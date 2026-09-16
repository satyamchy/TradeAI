"""Async SQLAlchemy database setup."""

import os
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base


def _database_url() -> str:
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError(
            "DATABASE_URL is required. Set your Supabase PostgreSQL URL in backend/.env."
        )

    if value.startswith("postgresql://"):
        value = value.replace("postgresql://", "postgresql+asyncpg://", 1)

    # Supabase URLs are commonly copied with sslmode=require. asyncpg expects
    # an `ssl` connection argument instead, so normalize that query parameter.
    if value.startswith("postgresql+asyncpg://"):
        parts = urlsplit(value)
        query = parse_qs(parts.query)
        query.pop("sslmode", None)
        clean_query = urlencode(query, doseq=True)
        value = urlunsplit((parts.scheme, parts.netloc, parts.path, clean_query, parts.fragment))

    return value


DATABASE_URL = _database_url()

connect_args = {"ssl": True} if "supabase.co" in DATABASE_URL else {}

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args=connect_args,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

Base = declarative_base()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    import app.db.models  # noqa: F401
    import app.db.models_trading  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
