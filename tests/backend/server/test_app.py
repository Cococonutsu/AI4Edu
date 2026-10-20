"""应用启动。"""

from __future__ import annotations

import logging

import httpx
import pytest

import ai4edu.server.app as app_module
from ai4edu.config import get_settings

pytestmark = pytest.mark.asyncio


async def test_missing_api_key_logged_at_startup(monkeypatch, caplog):
    """回归：错误记录 #12 —— 没配置 backend/.env 时发消息报 500。"""

    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    caplog.set_level(logging.ERROR, logger="ai4edu")

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
    assert "未配置 LLM_API_KEY" in caplog.text
