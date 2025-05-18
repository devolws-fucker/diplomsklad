from sqlalchemy import (
    ForeignKey, String, BigInteger, Integer, Text, Enum, DateTime, func
)
from sqlalchemy.orm import Mapped, DeclarativeBase, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from datetime import datetime
import enum

engine = create_async_engine("sqlite+aiosqlite:///db.sqlite3", echo=True)
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

class Operation(Base):
    __tablename__ = "operations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    type: Mapped[OperationType] = mapped_column(Enum(OperationType))
    quantity: Mapped[int] = mapped_column(default=1)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    user: Mapped["User"] = relationship(back_populates="operations")
    item: Mapped["Item"] = relationship(back_populates="operations", foreign_keys=[item_id])
    location: Mapped["Location"] = relationship(back_populates="operations")
    
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(50), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.worker)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    operations: Mapped[list["Operation"]] = relationship(back_populates="user")
    items: Mapped[list["Item"]] = relationship(back_populates="user")


class Location(Base):
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    code: Mapped[str] = mapped_column(String(50), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    items: Mapped[list["Item"]] = relationship(back_populates="location")
    operations: Mapped[list["Operation"]] = relationship(back_populates="location")


class Item(Base):
    __tablename__ = "items"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    barcode: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    quantity: Mapped[int] = mapped_column(default=0)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="stored")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    last_operation_id: Mapped[int | None] = mapped_column(ForeignKey("operations.id"), nullable=True)

    user: Mapped["User"] = relationship(back_populates="items")
    location: Mapped["Location"] = relationship(back_populates="items")
    operations: Mapped[list["Operation"]] = relationship(back_populates="item", foreign_keys=["Operation.item_id"])
    last_operation: Mapped["Operation | None"] = relationship(foreign_keys=[last_operation_id], lazy="joined")


class SyncLog(Base):
    __tablename__ = "sync_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int]
    status: Mapped[str] = mapped_column(String(20))
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
