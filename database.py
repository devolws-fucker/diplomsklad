from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from models import Base 

DATABASE_URL = "sqlite+aiosqlite:///db.sqlite3"  

engine = create_async_engine(DATABASE_URL, echo=True)
async_session = async_sessionmaker(bind=engine, expire_on_commit=False)

async def get_async_session():
    async with async_session() as session:
        yield session