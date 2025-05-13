from sqlalchemy import select, update, delete, func, DateTime
from models import async_session, User, Task
from pydantic import BaseModel, ConfigDict
from typing import List


class ItemSchema(BaseModel):
    id: int
    barcode: str
    name: str
    sku: str
    quantity: int
    location_id: int
    status: str
    updated_at: DateTime

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