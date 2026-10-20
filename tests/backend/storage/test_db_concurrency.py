"""数据库并发：长时间未结束的读事务不能让其他连接的写入失败。

辅导回合在等待模型返回（可能数分钟）时，引擎的会话里可能还开着一个读事务。
默认回滚日志模式下，这会让同时到来的请求报 "database is locked"。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from ai4edu.storage.db import make_engine

pytestmark = pytest.mark.asyncio


async def test_open_read_transaction_does_not_block_writer(tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "test.sqlite3", busy_timeout=1)
    try:
        async with engine.begin() as setup:
            await setup.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)"))
            await setup.execute(text("INSERT INTO t (v) VALUES ('a')"))

        async with engine.connect() as reader, engine.connect() as writer:
            # 读连接开启事务并保持不结束，模拟等待模型时未提交的会话。
            await reader.begin()
            rows = (await reader.execute(text("SELECT v FROM t"))).all()
            assert rows == [("a",)]

            # 另一个连接此时写入并提交，不能报 database is locked。
            await writer.begin()
            await writer.execute(text("INSERT INTO t (v) VALUES ('b')"))
            await writer.commit()

            await reader.rollback()

        async with engine.connect() as check:
            mode = (await check.execute(text("PRAGMA journal_mode"))).scalar()
            count = (await check.execute(text("SELECT count(*) FROM t"))).scalar()
        assert mode == "wal"
        assert count == 2
    finally:
        await engine.dispose()
