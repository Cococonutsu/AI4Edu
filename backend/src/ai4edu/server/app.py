"""FastAPI 应用工厂与入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import APIRouter, FastAPI

from ai4edu import __version__
from ai4edu.server.routes import attachments, auth, conversations, messages
from ai4edu.storage.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    # 密钥缺失的告警在 QueryEngine 构建处发出（首次创建引擎时），
    # 见 core/query_engine.py 与 core 的回归测试。
    yield


def create_app() -> FastAPI:
    application = FastAPI(title="AI4Edu", version=__version__, lifespan=lifespan)

    api = APIRouter(prefix="/api")

    @api.get("/health", tags=["health"])
    async def health() -> dict[str, bool]:
        return {"ok": True}

    api.include_router(auth.router)
    api.include_router(conversations.router)
    api.include_router(attachments.router)
    api.include_router(messages.router)

    application.include_router(api)
    return application


app = create_app()
