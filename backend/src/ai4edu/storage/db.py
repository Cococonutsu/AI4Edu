"""数据库连接与初始化。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
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


# 等待锁的秒数。一次辅导回合会在模型调用前后多次短暂写库，需要留出余量。
_BUSY_TIMEOUT_SECONDS = 30


def make_engine(db_path: Path, *, busy_timeout: float = _BUSY_TIMEOUT_SECONDS) -> AsyncEngine:
    """创建 SQLite 异步引擎，并为每个连接设置并发所需的参数。"""

    new_engine = create_async_engine(
        _database_url(db_path),
        echo=False,
        future=True,
        connect_args={"timeout": busy_timeout},
    )

    @event.listens_for(new_engine.sync_engine, "connect")
    def _configure_sqlite(dbapi_connection, connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        # SQLite 默认不开启外键，逐连接打开以支持级联删除。
        cursor.execute("PRAGMA foreign_keys=ON")
        # WAL：读不阻塞写、写不阻塞读。默认的回滚日志模式下，一个读事务
        # （例如等待模型返回时仍未结束的查询）会让其他连接的提交全部失败，
        # 报 "database is locked"。
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute(f"PRAGMA busy_timeout={int(busy_timeout * 1000)}")
        cursor.close()

    return new_engine


engine: AsyncEngine = make_engine(_settings.db_path)


async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _migrate_llm_calls(connection: AsyncConnection) -> None:
    """给已有的 `llm_calls` 表补新列（step、thinking），不重建、不删数据。"""

    rows = await connection.execute(text("PRAGMA table_info(llm_calls)"))
    existing = {str(row[1]) for row in rows}
    if "step" not in existing:
        await connection.execute(
            text("ALTER TABLE llm_calls ADD COLUMN step INTEGER")
        )
    if "thinking" not in existing:
        await connection.execute(
            text("ALTER TABLE llm_calls ADD COLUMN thinking VARCHAR(8)")
        )


async def init_db() -> None:
    """创建数据目录与全部表；可重复调用；旧库自动补列。"""
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await _migrate_llm_calls(connection)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：请求成功提交，异常回滚。"""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
