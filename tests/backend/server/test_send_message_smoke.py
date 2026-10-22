"""发消息主路径的端到端冒烟：不 monkeypatch get_engine。

回归：get_engine() 曾因 Reminders 未导入而 100% 抛 NameError，
所有既有测试都替换了引擎、真实路径零覆盖。
"""

from __future__ import annotations

import pytest

from ai4edu.server.streaming import runs

pytestmark = pytest.mark.asyncio


async def test_get_engine_builds_without_error():
    """组合根能正常构建（不替换任何依赖）。"""

    from ai4edu.server.routes.messages import get_engine

    engine = get_engine()
    assert engine is not None
