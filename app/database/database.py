from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import settings


# URL.create safely handles passwords containing @, /, : or %.
from sqlalchemy.engine import URL

DATABASE_URL = URL.create(
    "postgresql+asyncpg",
    username=settings.POSTGRES_USER,
    password=settings.POSTGRES_PASSWORD,
    host=settings.POSTGRES_HOST,
    port=settings.POSTGRES_PORT,
    database=settings.POSTGRES_DB,
)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session