from sqlalchemy import ForeignKey, String, BigInteger, Integer, Text, Enum, DateTime, func
from sqlalchemy.orm import Mapped, DeclarativeBase, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
import enum

engine = create_async_engine(url='sqlite+aiosqlite:///db.sqlite3', echo=True)

async_session = async_sessionmaker(bind=engine, expire_on_commit=False)


class Base(AsyncAttrs, DeclarativeBase):
    pass

class UserRole(str, enum.Enum):
    admin = "admin"
    worker = "worker"

class OperationType(str, enum.Enum):
    receive = "receive"
    move = "move"
    ship = "ship"
    inventory = "inventory"



class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id = mapped_column(BigInteger)
    username: Mapped[str] = mapped_column(String(50), nullable=True)
    last_login: Mapped[DateTime] = mapped_column(nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.worker)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[DateTime] = mapped_column(default=func.now())


class Item(Base):
    __tablename__ = 'items'

    id: Mapped[int] = mapped_column(primary_key=True)
    barcode: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    sku: Mapped[str] = mapped_column(String(100), nullable=True)
    quantity: Mapped[int] = mapped_column(default=0)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    description: Mapped[str] = mapped_column(Text, nullable=True)
    external_id: Mapped[str] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="stored")
    updated_at: Mapped[DateTime] = mapped_column(default=func.now(), onupdate=func.now())
    last_operation_id: Mapped[int] = mapped_column(ForeignKey("operations.id"), nullable=True)


class Location(Base):
    __tablename__ = 'locations'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    code: Mapped[str] = mapped_column(String(50), unique=True) 
    description: Mapped[str] = mapped_column(Text, nullable=True)


class Operation(Base):
    __tablename__ = 'operations'

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    type: Mapped[OperationType] = mapped_column(Enum(OperationType))
    quantity: Mapped[int] = mapped_column(default=1)
    note: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(default=func.now())


class Sync_log(Base):
    __tablename__ = 'sync_logs'

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(50))  # item, location, operation
    entity_id: Mapped[int]
    status: Mapped[str] = mapped_column(String(20))  # success | fail
    message: Mapped[str] = mapped_column(Text, nullable=True)
    synced_at: Mapped[DateTime] = mapped_column(default=func.now())
    

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)