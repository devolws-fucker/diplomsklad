from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends
import logging
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select, update, delete, func
from models import init_db, User, UserRole # Ensure Item is imported if you need it here, but typically it's used in requests.py
# Correctly aliasing requests.py functions as rq
import requests as rq # Renamed the import to avoid confusion with the 'requests' library
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_async_session
import os
from typing import Optional, List
from dotenv import load_dotenv
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Re-define Pydantic models here or import them from a shared schema file if you have one
# Assuming they are defined in main.py for now as per your original structure
class ScanItem(BaseModel):
    barcode: str

class ItemCreate(BaseModel):
    barcode: str
    name: str
    sku: Optional[str] = None
    location_id: Optional[int] = None
    quantity: int = 0
    note: Optional[str] = None
    user_tg_id: int

class OperationData(BaseModel):
    user_id: int
    item_id: int
    location_id: int
    type: str
    quantity: int = 1
    note: str = ""

class LocationCreate(BaseModel):
    name: str
    code: str
    description: Optional[str] = None

class LocationUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None

class SyncData(BaseModel):
    entity_type: str
    entity_id: int
    message: str = ""

class UserRegistration(BaseModel):
    tg_id: int
    username: str | None
    role: UserRole
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

# Existing endpoint
@app.post("/api/items/scan")
async def scan_item(data: ScanItem):
    return await rq.scan_or_create_item(data.barcode)

# NEW ENDPOINT TO CREATE AN ITEM
@app.post("/api/items")
async def create_item(item_data: ItemCreate):
    """
    Создает новый товар в базе данных.
    """
    try:
        # Pass the item_data directly to the requests module function
        new_item = await rq.create_item(item_data)
        return {"status": "ok", "item": new_item}
    except HTTPException as e:
        logger.error(f"HTTPException when creating item: {e.detail}, Status: {e.status_code}")
        raise e
    except Exception as e:
        logger.error(f"Unexpected error when creating item: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")


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

@app.post("/api/locations")
async def create_location(location_data: LocationCreate):
    return await rq.create_new_location(location_data)

@app.put("/api/locations/{location_id}")
async def update_location(location_id: int, location_data: LocationUpdate):
    return await rq.update_existing_location(location_id, location_data)

@app.delete("/api/locations/{location_id}")
async def delete_location(location_id: int):
    return await rq.delete_existing_location(location_id)

@app.get("/api/locations/{location_id}")
async def get_single_location(location_id: int, session: AsyncSession = Depends(get_async_session)):
    location = await rq.fetch_location_by_id(location_id, session)
    if not location:
        raise HTTPException(status_code=404, detail="Локация не найдена")
    return {"id": location.id, "name": location.name, "code": location.code, "description": location.description}

@app.post("/api/sync")
async def sync_to_1c(data: SyncData):
    return await rq.log_sync(data)

@app.post("/api/register")
async def register_user(registration_data: UserRegistration):
    try:
        return await rq.register_new_user(registration_data)
    except HTTPException as e:
        logger.error(f"Ошибка при регистрации пользователя (HTTPException): {e.detail}, Status: {e.status_code}")
        raise e
    except Exception as e:
        logger.error(f"Неожиданная ошибка при регистрации пользователя: {e}")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {e}")

@app.post("/api/check_admin_password")
async def check_admin_password(password_data: dict):
    password = password_data.get("password")
    ADMIN_PASSWORD = os.environ.get("ADMIN_REGISTRATION_PASSWORD")
    if password == ADMIN_PASSWORD:
        return {"status": "ok"}
    else:
        return {"status": "error"}