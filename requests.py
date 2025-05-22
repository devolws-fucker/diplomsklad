from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
import logging
from models import (
    User, Item, Location, Operation,
    OperationType, SyncLog, UserRole
)
from database import async_session
import os
from dotenv import load_dotenv
load_dotenv()
logger = logging.getLogger(__name__)

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
                await session.flush()
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

async def create_new_location(location_data):
    async with async_session() as session:
        async with session.begin():
            # Проверяем на уникальность кода локации
            existing_location = await session.scalar(
                select(Location).where(Location.code == location_data.code)
            )
            if existing_location:
                raise HTTPException(status_code=400, detail="Локация с таким кодом уже существует.")

            new_location = Location(
                name=location_data.name,
                code=location_data.code,
                description=location_data.description
            )
            session.add(new_location)
            await session.flush()
            await session.refresh(new_location)
            return {"status": "ok", "location": {"id": new_location.id, "name": new_location.name, "code": new_location.code, "description": new_location.description}}

async def update_existing_location(location_id: int, location_data):
    async with async_session() as session:
        async with session.begin():
            location = await session.scalar(select(Location).where(Location.id == location_id))
            if not location:
                raise HTTPException(status_code=404, detail="Локация не найдена")

            if location_data.code and location_data.code != location.code:
                existing_location = await session.scalar(
                    select(Location).where(Location.code == location_data.code, Location.id != location_id)
                )
                if existing_location:
                    raise HTTPException(status_code=400, detail="Локация с таким кодом уже существует.")

            if location_data.name is not None:
                location.name = location_data.name
            if location_data.code is not None:
                location.code = location_data.code
            if location_data.description is not None:
                location.description = location_data.description

            await session.flush()
            await session.refresh(location)
            return {"status": "ok", "location": {"id": location.id, "name": location.name, "code": location.code, "description": location.description}}

async def delete_existing_location(location_id: int):
    async with async_session() as session:
        async with session.begin():
            location = await session.scalar(select(Location).where(Location.id == location_id))
            if not location:
                raise HTTPException(status_code=404, detail="Локация не найдена")

            associated_items = await session.scalar(select(func.count(Item.id)).where(Item.location_id == location_id))
            associated_operations = await session.scalar(select(func.count(Operation.id)).where(Operation.location_id == location_id))

            if associated_items > 0 or associated_operations > 0:
                raise HTTPException(status_code=400, detail="Невозможно удалить локацию, так как с ней связаны товары или операции. Сначала переместите или удалите их.")
            
            await session.delete(location)
            await session.flush()
            return {"status": "ok", "message": f"Локация {location_id} удалена."}

async def fetch_location_by_id(location_id: int, session: AsyncSession):
    location = await session.scalar(select(Location).where(Location.id == location_id))
    return location

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

            await session.flush()
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
            await session.flush()
            return {"status": "synced"}

async def register_new_user(registration_data, external_session: AsyncSession = None):
    # Определяем, используем ли внешнюю сессию (например, из FastAPI Depends)
    # или создаем новую для этой функции.
    use_external_session = bool(external_session)
    session = external_session # Если external_session не None, то используем его

    # Если внешняя сессия не предоставлена, создаем свою собственную.
    # Это важно, так как FastAPI управляет сессиями, переданными через Depends.
    # Если функция вызывается без Depends, она должна управлять своей сессией сама.
    if not use_external_session:
        session = async_session()

    try:
        # async with session.begin(): гарантирует, что транзакция будет
        # автоматически зафиксирована при успешном выполнении блока
        # и откачена при возникновении исключения.
        async with session.begin():
            existing_user = await session.scalar(select(User).where(User.tg_id == registration_data.tg_id))
            if existing_user:
                logger.warning(f"Пользователь с TG ID {registration_data.tg_id} уже зарегистрирован.")
                raise HTTPException(
                    status_code=409, # 409 Conflict - ресурс уже существует
                    detail="Пользователь с таким Telegram ID уже зарегистрирован."
                )

            if registration_data.role == UserRole.admin:
                admin_password = os.environ.get("ADMIN_REGISTRATION_PASSWORD")
                if not admin_password or registration_data.admin_password != admin_password:
                    raise HTTPException(status_code=403, detail="Неверный пароль администратора.") # Используем HTTPException

            new_user = User(
                tg_id=registration_data.tg_id,
                username=registration_data.username,
                role=registration_data.role,
                # Telegram user's first_name and last_name are not in UserRegistration model
                # If you want to store them, you need to add them to UserRegistration and pass them from frontend
            )
            session.add(new_user)

            await session.flush() # Применяет изменения к сессии, но не коммитит в БД
            await session.refresh(new_user) # Загружает свежие данные, включая ID

            print(f"Зарегистрирован новый пользователь: {new_user.__dict__}")

            return {
                "id": new_user.id,
                "tg_id": new_user.tg_id,
                "username": new_user.username,
                "first_name": new_user.first_name, # Эти поля будут null, если их нет в new_user
                "last_name": new_user.last_name,   # Нужно убедиться, что они заполняются при регистрации
                "last_login": new_user.last_login,
                "role": new_user.role.value,
                "is_active": new_user.is_active,
                "created_at": new_user.created_at.isoformat() if new_user.created_at else None,
            }
    except Exception as e:
        # Исключение будет перехвачено и обработано в main.py
        # async with session.begin(): уже выполнит rollback, если произошла ошибка
        logger.error(f"Ошибка при регистрации пользователя в requests.py: {e}")
        raise # Важно: перевыбрасываем исключение, чтобы оно дошло до main.py
    finally:
        # Закрываем сессию только если мы ее создали (т.е. не использовали внешнюю)
        if not use_external_session:
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