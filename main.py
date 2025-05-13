from contextlib import asynccontextmanager

from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from sqlalchemy import select

from models import (
    init_db, async_session, User, Item, Operation, Location, OperationType, Sync_log
)
from datetime import datetime
from requests import get_user_by_tg_id
import requests as rq


@asynccontextmanager
async def lifespan(app_: FastAPI):
    await init_db()
    print('Bot is ready')
    yield


app = FastAPI(title='DiplomSklad', lofespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


class ScanRequest(BaseModel):
    barcode: str

@app.post("/api/items/scan")
async def scan_item(req: ScanRequest):
    async with async_session() as session:
        item = await session.scalar(select(Item).where(Item.barcode == req.barcode))
        if item:
            return {"status": "exists", "item": item}
        
        # Создание нового товара с пустыми данными
        new_item = Item(barcode=req.barcode, name="Новый товар", quantity=0)
        session.add(new_item)
        await session.commit()
        await session.refresh(new_item)
        return {"status": "created", "item": new_item}
    
class OperationRequest(BaseModel):
    user_id: int
    item_id: int
    location_id: int
    type: OperationType
    quantity: int = 1
    note: str = ""

@app.get("/api/users/{tg_id}")
async def get_user(tg_id: int):
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.tg_id == tg_id))
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        return {
            "id": user.id,
            "tg_id": user.tg_id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "is_active": user.is_active,
            "created_at": user.created_at,
        }
    
@app.get("/api/items/{tg_id}")
async def get_items(tg_id: int):
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.tg_id == tg_id))
        if not user:
            user = User(tg_id=tg_id, first_name="?", last_name="?", role="worker")
            session.add(user)
            await session.commit()
            await session.refresh(user)

        result = await session.execute(select(Item))
        items = result.scalars().all()
        return [
            {
                "id": item.id,
                "barcode": item.barcode,
                "name": item.name,
                "sku": item.sku,
                "quantity": item.quantity,
                "location_id": item.location_id,
                "status": item.status,
                "updated_at": item.updated_at,
            }
            for item in items
        ]

@app.post("/api/operations")
async def create_operation(data: OperationRequest):
    async with async_session() as session:
        operation = Operation(
            user_id=data.user_id,
            item_id=data.item_id,
            location_id=data.location_id,
            type=data.type,
            quantity=data.quantity,
            note=data.note
        )
        session.add(operation)

        # Обновим количество товара
        item = await session.get(Item, data.item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        
        if data.type == OperationType.receive:
            item.quantity += data.quantity
        elif data.type == OperationType.ship:
            item.quantity -= data.quantity
        elif data.type == OperationType.inventory:
            item.quantity = data.quantity
        # При перемещении меняем location_id
        if data.type == OperationType.move:
            item.location_id = data.location_id

        await session.commit()
        await session.refresh(operation)
        return {"status": "ok", "operation_id": operation.id}
    
@app.get("/api/locations", response_model=List[dict])
async def get_locations():
    async with async_session() as session:
        locations = (await session.execute(select(Location))).scalars().all()
        return [{"id": l.id, "name": l.name, "code": l.code} for l in locations]
    
class SyncRequest(BaseModel):
    entity_type: str
    entity_id: int
    message: str = ""

@app.post("/api/sync")
async def sync_to_1c(data: SyncRequest):
    async with async_session() as session:
        log = Sync_log(
            entity_type=data.entity_type,
            entity_id=data.entity_id,
            status="success",
            message=data.message
        )
        session.add(log)
        await session.commit()
        return {"status": "synced"}