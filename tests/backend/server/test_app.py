"""应用启动。"""

from __future__ import annotations

import httpx
import pytest

import ai4edu.server.app as app_module

pytestmark = pytest.mark.asyncio


async def test_startup_initializes_database_and_serves_health(monkeypatch):
    """应用能启动、健康检查可用。

    密钥缺失的告警在 QueryEngine 构建处发出（回归 #12 的对应测试在
    tests/backend/core/test_query_engine.py），启动本身不因缺密钥失败。
    """

    async def fake_init_db() -> None:
        return None

    monkeypatch.setattr(app_module, "init_db", fake_init_db)
    app = app_module.create_app()

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get("/api/health")

    assert response.status_code == 200
