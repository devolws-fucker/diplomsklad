from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
import logging
from models import (
    User, Item, Location, Operation,
    OperationType, SyncLog, UserRole
)
from database import async_session # Assuming database.py has async_session
import os
from dotenv import load_dotenv
load_dotenv()
logger = logging.getLogger(__name__)

# Assuming this comes from main.py's Pydantic models or a shared schema file
# class ItemCreate(BaseModel): # You might need to import this or define it here if not shared
#     barcode: str
#     name: str
#     sku: Optional[str] = None
#     location_id: Optional[int] = None
#     quantity: int
#     note: Optional[str] = None


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
                # When an item is 'created' (doesn't exist yet),
                # you return a basic item dict.
                # The actual creation happens via the /api/items POST endpoint.
                return {"status": "created", "item": {"barcode": barcode, "name": "Новый товар"}}

# NEW FUNCTION TO CREATE AN ITEM
async def create_item(item_data): # item_data будет экземпляром ItemCreate Pydantic модели
    async with async_session() as session:
        async with session.begin():
            # Проверка на уникальность штрихкода
            existing_item = await session.scalar(select(Item).where(Item.barcode == item_data.barcode))
            if existing_item:
                raise HTTPException(status_code=400, detail="Товар с таким штрихкодом уже существует.")

            # Проверка наличия локации
            if item_data.location_id:
                location = await session.scalar(select(Location).where(Location.id == item_data.location_id))
                if not location:
                    raise HTTPException(status_code=400, detail="Указанная локация не найдена.")
            else:
                raise HTTPException(status_code=400, detail="Локация для нового товара должна быть указана.")

            # Найдите внутреннего пользователя по user_tg_id, пришедшему с фронтенда
            user_from_db = await session.scalar(select(User).where(User.tg_id == item_data.user_tg_id)) # <--- ИСПОЛЬЗУЕМ user_tg_id ИЗ ItemCreate
            if not user_from_db:
                raise HTTPException(status_code=400, detail="Пользователь Telegram не найден в базе данных. Пожалуйста, убедитесь, что вы зарегистрированы.")


            new_item = Item(
                barcode=item_data.barcode,
                name=item_data.name,
                sku=item_data.sku,
                location_id=item_data.location_id,
                quantity=item_data.quantity,
                description=item_data.note,
                user_id=user_from_db.id, # <--- ЭТО САМОЕ ВАЖНОЕ: Используем внутренний ID пользователя
            )
            session.add(new_item)
            await session.flush()
            await session.refresh(new_item)

            return serialize_item(new_item)


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

            if not item:
                raise HTTPException(status_code=404, detail="Товар не найден.")
            if not user:
                raise HTTPException(status_code=404, detail="Пользователь не найден.")
            if not location:
                raise HTTPException(status_code=404, detail="Локация не найдена.")

            if op.type == "ship" and item.quantity < op.quantity:
                raise HTTPException(status_code=400, detail="Недостаточно товара для отгрузки.")

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
                # For move operation, quantity on the item doesn't change, only location
                item.location_id = location.id
                # If quantity is provided for move, it implies moving 'op.quantity' from current location
                # to new location. This requires more complex logic (deduct from old, add to new)
                # For simplicity here, assuming 'move' means moving the *entire* item record to a new location.
                # If partial moves are intended, item.quantity needs to be handled differently (e.g., create new item record for moved quantity).
                # The current `move` implementation in `ScanItem.vue` only takes a `location_id`, not quantity, for move.
                # So if `quantity` is used in `OperationData` for move, it might be extraneous or imply a specific behavior.
                # Let's assume the frontend sends quantity 1 for move and we just update location.
                # If partial moves are desired, the logic needs to be more complex.
                pass # Location update is already handled by item.location_id = location.id

            item.last_operation_id = operation.id # Update the last operation ID

            await session.flush()
            # No need to refresh item explicitly if only quantity and last_operation_id are changed
            # These changes are reflected in the session and will be committed.
            # Refreshing operation might be useful if you need its ID immediately before returning.
            await session.refresh(operation)

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
    # Determine if we're using an external session (e.g., from FastAPI Depends)
    # or creating a new one for this function.
    use_external_session = bool(external_session)
    session = external_session # If external_session is not None, use it

    # If an external session is not provided, create our own.
    if not use_external_session:
        session = async_session()

    try:
        async with session.begin(): # This block manages the transaction (commit/rollback)
            existing_user = await session.scalar(select(User).where(User.tg_id == registration_data.tg_id))
            if existing_user:
                logger.warning(f"Пользователь с TG ID {registration_data.tg_id} уже зарегистрирован.")
                raise HTTPException(
                    status_code=409, # 409 Conflict - resource already exists
                    detail="Пользователь с таким Telegram ID уже зарегистрирован."
                )

            if registration_data.role == UserRole.admin:
                admin_password = os.environ.get("ADMIN_REGISTRATION_PASSWORD")
                if not admin_password or registration_data.admin_password != admin_password:
                    raise HTTPException(status_code=403, detail="Неверный пароль администратора.")

            new_user = User(
                tg_id=registration_data.tg_id,
                username=registration_data.username,
                role=registration_data.role,
            )
            session.add(new_user)

            await session.flush() # Apply changes to the session, but don't commit to DB yet
            await session.refresh(new_user) # Load fresh data, including ID

            print(f"Зарегистрирован новый пользователь: {new_user.__dict__}")

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
        logger.error(f"Ошибка при регистрации пользователя в requests.py: {e}")
        raise # Re-raise the exception to be caught by main.py's handler
    finally:
        if not use_external_session:
            await session.close() # Close session only if we created it

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