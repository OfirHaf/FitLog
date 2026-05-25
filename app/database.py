"""
Database initialization and connection management.
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from app.config import settings

DATABASE_URL = settings.database_url

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    connect_args={
        "timeout": 15,
        "check_same_thread": False,
    },
    poolclass=StaticPool,
)

async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def create_db_and_tables():
    """Create all database tables."""
    async with engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        await conn.exec_driver_sql("PRAGMA foreign_keys = ON")
        await conn.exec_driver_sql("PRAGMA synchronous=NORMAL")
        await conn.exec_driver_sql("PRAGMA cache_size=-64000")
        await conn.exec_driver_sql("PRAGMA temp_store=MEMORY")
        await conn.run_sync(_migrate_add_profile_id_sqlite)
        await conn.run_sync(_migrate_add_role_sqlite)
        await conn.run_sync(SQLModel.metadata.create_all)


def _migrate_add_profile_id_sqlite(sync_conn):
    """
    Legacy schema migration shim for existing SQLite databases.

    Adds profile_id column to workout_logs and macro_entries if missing.
    This runs idempotently at startup for backwards compatibility with databases
    created before the Alembic migration was added.

    New installations: these columns are created by SQLModel.metadata.create_all().
    Existing installations: this shim adds the columns without data loss.
    """
    result = sync_conn.exec_driver_sql("PRAGMA table_info(workout_logs)")
    columns = [row[1] for row in result.fetchall()]
    # Only ALTER if the table exists (non-empty columns) but is missing profile_id.
    # On fresh databases the table does not exist yet; create_all creates it correctly.
    if columns and "profile_id" not in columns:
        sync_conn.exec_driver_sql(
            "ALTER TABLE workout_logs ADD COLUMN profile_id VARCHAR"
        )
        sync_conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_workout_logs_profile_id ON workout_logs(profile_id)"
        )

    result = sync_conn.exec_driver_sql("PRAGMA table_info(macro_entries)")
    columns = [row[1] for row in result.fetchall()]
    if columns and "profile_id" not in columns:
        sync_conn.exec_driver_sql(
            "ALTER TABLE macro_entries ADD COLUMN profile_id VARCHAR"
        )
        sync_conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_macro_entries_profile_id ON macro_entries(profile_id)"
        )


def _migrate_add_role_sqlite(sync_conn):
    """
    Legacy schema migration shim: adds the `role` column to `users` if missing.
    Runs idempotently at startup for databases created before role-based access
    was introduced. New installations get the column via SQLModel.metadata.create_all().
    """
    result = sync_conn.exec_driver_sql("PRAGMA table_info(users)")
    columns = [row[1] for row in result.fetchall()]
    if columns and "role" not in columns:
        sync_conn.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN role VARCHAR DEFAULT 'user'"
        )


async def get_session() -> AsyncSession:
    """Get a database session."""
    async with async_session_maker() as session:
        yield session
