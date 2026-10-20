"""后端测试共用配置：隔离数据目录与临时数据库。

`ai4edu.storage.db` 在导入时就用当时的 `Settings` 创建了引擎，所以需要数据库的
测试一律用 `make_engine(tmp_path / ...)` 自建引擎，不使用进程级 `async_session`。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

# 必须早于 `ai4edu.storage.db` 的导入：该模块在导入时就用 Settings 创建了引擎。
# 把进程级数据目录指到临时目录，任何误用进程级引擎的测试也不会写仓库的 data/。
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="ai4edu-test-data-")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
)

from ai4edu.config import get_settings  # noqa: E402
from ai4edu.storage.db import make_engine  # noqa: E402
from ai4edu.storage.models import Base, Conversation, User  # noqa: E402

# 让各子目录的测试都能 `from fakes import ...`。
sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """把所有测试的数据目录指到临时目录，避免写入仓库的 `data/`。"""

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def db_engine(tmp_path: Path):
    engine = make_engine(tmp_path / "test.sqlite3")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def session_factory(db_engine):
    return async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )


@pytest_asyncio.fixture
async def db_session(session_factory):
    async with session_factory() as session:
        yield session


@pytest.fixture
def seed(session_factory):
    """创建一名学生和一个会话，返回 `(user, conversation_id)`。"""

    async def _seed(
        *,
        phase: str = "idle",
        state_json: dict | None = None,
        grade_band: str = "junior",
        grade: int = 8,
        title: str = "新对话",
    ) -> tuple[User, int]:
        async with session_factory() as session:
            user = User(
                username=f"student_{uuid4().hex[:10]}",
                password_hash="not-used",
                display_name="小明",
                grade_band=grade_band,
                grade=grade,
                role="student",
                is_active=True,
            )
            session.add(user)
            await session.flush()
            conversation = Conversation(
                user_id=user.id,
                title=title,
                phase=phase,
                state_json=state_json,
            )
            session.add(conversation)
            await session.flush()
            await session.commit()
            return user, conversation.id

    return _seed
