from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from models import init_db, User, UserRole
import requests as rq
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_async_session
import os

class ScanItem(BaseModel):
    barcode: str

class OperationData(BaseModel):
    user_id: int
    item_id: int
    location_id: int
    type: str
    quantity: int = 1
    note: str = ""

class SyncData(BaseModel):
    entity_type: str
    entity_id: int
    message: str = ""

class UserRegistration(BaseModel):
    tg_id: int
    username: str | None
    role: str
    admin_password: str | None = None

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

@app.post("/api/items/scan")
async def scan_item(data: ScanItem):
    return await rq.scan_or_create_item(data.barcode)

@app.get("/api/users/{tg_id}")
async def get_user(tg_id: int, session: AsyncSession = Depends(get_async_session)):
    user = await rq.fetch_user_by_tg_id(tg_id, session)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user

@app.get("/api/users/{tg_id}/items")
async def get_user_items(tg_id: int):
    return await rq.get_items_by_user_tg(tg_id)

@app.post("/api/operations")
async def create_operation(op: OperationData):
    return await rq.process_operation(op)

@app.get("/api/locations")
async def get_locations():
    return await rq.fetch_all_locations()

@app.post("/api/sync")
async def sync_to_1c(data: SyncData):
    return await rq.log_sync(data)

@app.post("/api/register")
async def register_user(registration_data: UserRegistration, session: AsyncSession = Depends(get_async_session)):
    try:
        user = await rq.register_new_user(registration_data, session)
        return user
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/check_admin_password")
async def check_admin_password(password_data: dict):
    password = password_data.get("password")
    HARDCODED_ADMIN_PASSWORD = "11"
    if password == HARDCODED_ADMIN_PASSWORD:
        return {"status": "ok"}
    else:
        return {"status": "error"}
#@app.post("/api/check_admin_password")
#async def check_admin_password(password_data: dict):
#    password = password_data.get("password")
#    ADMIN_PASSWORD = os.environ.get("ADMIN_REGISTRATION_PASSWORD")
#    if password == ADMIN_PASSWORD:
#        return {"status": "ok"}
#    else:
#        return {"status": "error"}