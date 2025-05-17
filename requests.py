from datetime import datetime
from enum import Enum
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Enum as PgEnum, Boolean
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite+aiosqlite:///./warehouse.db"

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


class OperationType(str, Enum):
    receive = "receive"
    ship = "ship"
    move = "move"
    inventory = "inventory"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    tg_id = Column(Integer, unique=True, nullable=False)
    username = Column(String, nullable=True)
    role = Column(String, default="worker")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, default=datetime.utcnow)

    operations = relationship("Operation", back_populates="user")


class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    code = Column(String, unique=True, nullable=True)
    description = Column(String, nullable=True)

    items = relationship("Item", back_populates="location")
    operations = relationship("Operation", back_populates="location")


class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True)
    barcode = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    sku = Column(String, nullable=True)
    quantity = Column(Integer, default=0)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    last_operation_id = Column(Integer, ForeignKey("operations.id"), nullable=True)

    location = relationship("Location", back_populates="items")
    operations = relationship("Operation", back_populates="item", foreign_keys="Operation.item_id")
    last_operation = relationship("Operation", foreign_keys=[last_operation_id], post_update=True)


class Operation(Base):
    __tablename__ = "operations"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    item_id = Column(Integer, ForeignKey("items.id"))
    location_id = Column(Integer, ForeignKey("locations.id"))
    type = Column(PgEnum(OperationType), nullable=False)
    quantity = Column(Integer, default=1)
    note = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="operations")
    item = relationship("Item", back_populates="operations", foreign_keys=[item_id])
    location = relationship("Location", back_populates="operations")


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id = Column(Integer, primary_key=True)
    entity_type = Column(String, nullable=False)
    entity_id = Column(Integer, nullable=False)
    status = Column(String, default="success")
    message = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
