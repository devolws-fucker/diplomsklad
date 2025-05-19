from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from models import (
    User, Item, Location, Operation,
    OperationType, SyncLog, UserRole
)
from database import async_session
import os
from dotenv import load_dotenv
load_dotenv()

async def fetch_user_by_tg_id(tg_id: int, session: AsyncSession):
    async with session.begin():
        user = await session.scalar(select(User).where(User.tg_id == tg_id))
        return user

async def get_items_by_user_tg(tg_id: int):
    async with async_session() as session:
        async with session.begin():
            user = await session.scalar(select(User).where(User.tg_id == tg_id))
            if not user:
                user = User(tg_id=tg_id)
                session.add(user)
                await session.commit()
                await session.refresh(user)

            items = await session.scalars(select(Item).where(Item.user_id == user.id))
            return [serialize_item(item) for item in items]

async def scan_or_create_item(barcode: str):
    async with async_session() as session:
        async with session.begin():
            item = await session.scalar(select(Item).where(Item.barcode == barcode))
            if item:
                return {"status": "exists", "item": serialize_item(item)}
            else:
                return {"status": "created", "item": {"barcode": barcode, "name": "Новый товар"}}

async def fetch_all_locations():
    async with async_session() as session:
        async with session.begin():
            locations = await session.scalars(select(Location))
            return [{"id": loc.id, "name": loc.name, "code": loc.code, "description": loc.description} for loc in locations]

async def process_operation(op):
    async with async_session() as session:
        async with session.begin():
            item = await session.get(Item, op.item_id)
            user = await session.get(User, op.user_id)
            location = await session.get(Location, op.location_id)

            if not item or not user or not location:
                raise Exception("Ошибка: сущность не найдена")

            if op.type == "ship" and item.quantity < op.quantity:
                raise Exception("Недостаточно товара")

            operation = Operation(
                user_id=user.id,
                item_id=item.id,
                location_id=location.id,
                type=OperationType(op.type),
                quantity=op.quantity,
                note=op.note
            )
            session.add(operation)

            if op.type == "receive":
                item.quantity += op.quantity
            elif op.type == "ship":
                item.quantity -= op.quantity
            elif op.type == "inventory":
                item.quantity = op.quantity
            elif op.type == "move":
                item.location_id = location.id

            item.last_operation_id = operation.id

            await session.commit()
            return {"status": "ok", "operation_id": operation.id}

async def log_sync(data):
    async with async_session() as session:
        async with session.begin():
            log = SyncLog(
                entity_type=data.entity_type,
                entity_id=data.entity_id,
                status="success",
                message=data.message
            )
            session.add(log)
            await session.commit()
            return {"status": "synced"}

async def register_new_user(registration_data, external_session: AsyncSession = None):
    use_external_session = bool(external_session)
    session = external_session if use_external_session else async_session()
    try:
        async with session.begin():
            existing_user = await session.scalar(select(User).where(User.tg_id == registration_data.tg_id))
            if existing_user:
                raise Exception("Пользователь с таким Telegram ID уже зарегистрирован.")

            if registration_data.role == "admin":
                admin_password = os.environ.get("ADMIN_REGISTRATION_PASSWORD")
                if not admin_password or registration_data.admin_password != admin_password:
                    raise Exception("Неверный пароль администратора.")

            new_user = User(
                tg_id=registration_data.tg_id,
                username=registration_data.username,
                role=UserRole(registration_data.role),
            )
            session.add(new_user)

            await session.commit()
            await session.refresh(new_user)

            print(f"Зарегистрирован новый пользователь: {new_user.__dict__}")  # Добавлено логирование

            return {
                "id": new_user.id,
                "tg_id": new_user.tg_id,
                "username": new_user.username,
                "first_name": new_user.first_name,
                "last_name": new_user.last_name,
                "last_login": new_user.last_login,
                "role": new_user.role.value,
                "is_active": new_user.is_active,
                "created_at": new_user.created_at.isoformat() if new_user.created_at else None,
            }
    except Exception as e:
        print(f"Ошибка при регистрации пользователя: {e}")  # Логирование ошибки
        raise
    finally:
        if not use_external_session and session:
            await session.close()

def serialize_item(item: Item):
    return {
        "id": item.id,
        "user_id": item.user_id,
        "barcode": item.barcode,
        "name": item.name,
        "sku": item.sku,
        "quantity": item.quantity,
        "location_id": item.location_id,
        "description": item.description,
        "external_id": item.external_id,
        "status": item.status,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "last_operation_id": item.last_operation_id,
    }