from sqlalchemy import select
from models import async_session, User, UserRole, OperationType
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from typing import List, Optional


class UserSchema(BaseModel):
    id: int
    tg_id: int
    username: Optional[str]
    last_login: Optional[datetime]
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ItemBaseSchema(BaseModel):
    barcode: str
    name: str
    sku: Optional[str] = None
    quantity: int
    location_id: int
    description: Optional[str] = None
    external_id: Optional[str] = None
    status: str = "stored"

class ItemCreateSchema(ItemBaseSchema):
    pass

class ItemUpdateSchema(ItemBaseSchema):
    pass

class ItemSchema(ItemBaseSchema):
    id: int
    updated_at: datetime
    last_operation_id: Optional[int]

    model_config = ConfigDict(from_attributes=True)


# === Location ===
class LocationSchema(BaseModel):
    id: int
    name: str
    code: str
    description: Optional[str]

    model_config = ConfigDict(from_attributes=True)


# === Operation ===
class OperationCreateSchema(BaseModel):
    user_id: int
    item_id: int
    location_id: int
    type: OperationType
    quantity: int
    note: Optional[str] = None

class OperationSchema(OperationCreateSchema):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

async def add_user(tg_id):
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.tg_id == tg_id))
        if user:
            return user
        
        new_user = User(tg_id=tg_id)
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)
        return new_user
    
async def get_user_by_tg_id(tg_id: int):
    async with async_session() as session:
        return await session.scalar(select(User).where(User.tg_id == tg_id))