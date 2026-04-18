from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hr_agent.config import get_settings
from hr_agent.db.models import Base

settings = get_settings()

# SQLite waits this many seconds for a write lock. Short default fails with
# OperationalError when another tool (e.g. DB Browser) holds the DB open.
_SQLITE_CONNECT_ARGS = {"timeout": 30.0}

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args=_SQLITE_CONNECT_ARGS if settings.database_url.startswith("sqlite") else {},
)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
