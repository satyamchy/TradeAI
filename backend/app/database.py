import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Default to SQLite with aiosqlite for simple local zero-config execution,
# or use PostgreSQL URL from environment if configured.
DATABASE_URL = os.getenv(
    "DATABASE_URL", "sqlite+aiosqlite:///./oneai_stock_analyzer.db"
)

# Replace postgresql:// with postgresql+asyncpg:// if needed
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migrate new columns if using SQLite
        if "sqlite" in DATABASE_URL:
            def _migrate_sqlite(sync_conn):
                res = sync_conn.exec_driver_sql("PRAGMA table_info(stock_analysis_snapshots);")
                existing_cols = [r[1] for r in res.fetchall()]
                needed = [
                    ("analysis_date", "TEXT DEFAULT ''"),
                    ("target_price", "REAL"),
                    ("stop_loss", "REAL"),
                    ("recommendation", "TEXT DEFAULT 'HOLD'"),
                    ("macro_score", "REAL DEFAULT 50.0"),
                    ("ai_reasoning", "TEXT"),
                ]
                for col_name, col_type in needed:
                    if col_name not in existing_cols:
                        try:
                            sync_conn.exec_driver_sql(f"ALTER TABLE stock_analysis_snapshots ADD COLUMN {col_name} {col_type};")
                        except Exception:
                            pass
            await conn.run_sync(_migrate_sqlite)
