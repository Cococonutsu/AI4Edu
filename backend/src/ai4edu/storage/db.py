"""数据库连接与初始化。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ai4edu.config import get_settings
from ai4edu.storage.models import Base

_settings = get_settings()


def _database_url(db_path: Path) -> str:
    return f"sqlite+aiosqlite:///{db_path}"


engine: AsyncEngine = create_async_engine(
    _database_url(_settings.db_path),
    echo=False,
    future=True,
)


@event.listens_for(engine.sync_engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:  # noqa: ANN001
    """SQLite 默认不开启外键，逐连接显式打开以支持级联删除。"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """创建数据目录与全部表；可重复调用。"""
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：请求成功提交，异常回滚。"""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
