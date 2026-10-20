"""`init_db` 对旧 `llm_calls` 表的轻量迁移：补列不删数据。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

import ai4edu.storage.db as db_module
from ai4edu.storage.db import init_db, make_engine

pytestmark = pytest.mark.asyncio


async def test_init_db_adds_missing_columns_to_existing_table(
    tmp_path: Path, monkeypatch
):
    db_path = tmp_path / "old.sqlite3"

    # 先用旧结构建库（没有 step / thinking 列）并插入一条旧数据。
    setup = make_engine(db_path)
    async with setup.begin() as connection:
        await connection.execute(
            text(
                """
                CREATE TABLE llm_calls (
                    id INTEGER PRIMARY KEY,
                    conversation_id INTEGER,
                    purpose VARCHAR(16) NOT NULL,
                    model VARCHAR(100) NOT NULL,
                    prompt_version VARCHAR(50),
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    latency_ms INTEGER,
                    error TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        await connection.execute(
            text(
                "INSERT INTO llm_calls (purpose, model) "
                "VALUES ('tutor', 'glm-5.3-flash')"
            )
        )
    await setup.dispose()

    # init_db 面向这个旧库执行：create_all 跳过已存在的表，迁移补列。
    engine = make_engine(db_path)
    monkeypatch.setattr(db_module, "engine", engine)
    try:
        await init_db()
        async with engine.connect() as connection:
            columns = {
                str(row[1])
                for row in await connection.execute(
                    text("PRAGMA table_info(llm_calls)")
                )
            }
            rows = (
                await connection.execute(
                    text("SELECT id, purpose, model FROM llm_calls")
                )
            ).all()
    finally:
        await engine.dispose()

    assert {"step", "thinking"} <= columns
    assert rows == [(1, "tutor", "glm-5.3-flash")]


async def test_init_db_is_idempotent(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "fresh.sqlite3"
    engine = make_engine(db_path)
    monkeypatch.setattr(db_module, "engine", engine)
    try:
        await init_db()
        await init_db()
        async with engine.connect() as connection:
            columns = [
                str(row[1])
                for row in await connection.execute(
                    text("PRAGMA table_info(llm_calls)")
                )
            ]
    finally:
        await engine.dispose()

    assert columns.count("step") == 1
    assert columns.count("thinking") == 1
