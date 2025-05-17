from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from pydantic import BaseModel
from sqlalchemy import select

from models import (
    init_db, async_session,
    Item, User, Operation, Location, OperationType, SyncLog
)
from requests import (
    get_user_by_tg_id,
    get_item_by_barcode,
    get_all_items,
    get_all_locations,
    get_location_by_id,
    get_user_by_id
)
from datetime import datetime


@asynccontextmanager
async def lifespan(app_: FastAPI):
    await init_db()
    print("Backend initialized")
    yield


app = FastAPI(title="DiplomSklad", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- SCHEMAS ---

class ScanRequest(BaseModel):
    barcode: str

class OperationRequest(BaseModel):
    user_id: int
    item_id: int
    location_id: int
    type: OperationType
    quantity: int = 1
    note: str = ""

class SyncRequest(BaseModel):
    entity_type: str
    entity_id: int
    message: str = ""


# --- ENDPOINTS ---

@app.post("/api/items/scan")
async def scan_item(req: ScanRequest):
    async with async_session() as session:
        item = await get_item_by_barcode(session, req.barcode)
        if item:
            return {"status": "exists", "item": {
                "id": item.id,
                "barcode": item.barcode,
                "name": item.name,
                "sku": item.sku,
                "quantity": item.quantity,
                "location_id": item.location_id,
                "status": item.status,
                "updated_at": item.updated_at,
            }}

        new_item = Item(barcode=req.barcode, name="Новый товар", quantity=0)
        session.add(new_item)
        await session.commit()
        await session.refresh(new_item)
        return {"status": "created", "item": {
            "id": new_item.id,
            "barcode": new_item.barcode,
            "name": new_item.name,
            "sku": new_item.sku,
            "quantity": new_item.quantity,
            "location_id": new_item.location_id,
            "status": new_item.status,
            "updated_at": new_item.updated_at,
        }}


@app.get("/api/users/{tg_id}")
async def get_user(tg_id: int):
    async with async_session() as session:
        user = await get_user_by_tg_id(session, tg_id)
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        return {
            "id": user.id,
            "tg_id": user.tg_id,
            "username": user.username,
            "role": user.role,
            "is_active": user.is_active,
            "created_at": user.created_at,
            "last_login": user.last_login
        }


@app.get("/api/items/{tg_id}")
async def get_items(tg_id: int):
    async with async_session() as session:
        user = await get_user_by_tg_id(session, tg_id)
        if not user:
            new_user = User(tg_id=tg_id)
            session.add(new_user)
            await session.commit()
            await session.refresh(new_user)
            user = new_user

        items = await get_all_items(session)
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
        item = await session.get(Item, data.item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Товар не найден")

        user = await get_user_by_id(session, data.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        location = await get_location_by_id(session, data.location_id)
        if not location:
            raise HTTPException(status_code=404, detail="Локация не найдена")

        operation = Operation(
            user_id=user.id,
            item_id=item.id,
            location_id=location.id,
            type=data.type,
            quantity=data.quantity,
            note=data.note
        )
        session.add(operation)

        if data.type == OperationType.receive:
            item.quantity += data.quantity
        elif data.type == OperationType.ship:
            item.quantity -= data.quantity
        elif data.type == OperationType.inventory:
            item.quantity = data.quantity
        elif data.type == OperationType.move:
            item.location_id = data.location_id

        item.last_operation_id = operation.id

        await session.commit()
        await session.refresh(operation)

        return {"status": "ok", "operation_id": operation.id}


@app.get("/api/locations")
async def get_locations():
    async with async_session() as session:
        locations = await get_all_locations(session)
        return [
            {
                "id": loc.id,
                "name": loc.name,
                "code": loc.code,
                "description": loc.description,
            }
            for loc in locations
        ]


@app.post("/api/sync")
async def sync_to_1c(data: SyncRequest):
    async with async_session() as session:
        log = SyncLog(
            entity_type=data.entity_type,
            entity_id=data.entity_id,
            status="success",
            message=data.message,
        )
        session.add(log)
        await session.commit()
        return {"status": "synced"}
