from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from models import init_db
import requests as rq


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
async def get_user(tg_id: int):
    return await rq.fetch_user_by_tg_id(tg_id)


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
