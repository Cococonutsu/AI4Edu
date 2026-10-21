"""FastAPI 应用工厂与入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
import logging

from fastapi import APIRouter, FastAPI

from ai4edu import __version__
from ai4edu.api.client import llm_credentials
from ai4edu.server.routes import attachments, auth, conversations, messages
from ai4edu.config import get_settings
from ai4edu.storage.db import init_db

logger = logging.getLogger("ai4edu")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    _, api_key = llm_credentials(get_settings())
    if not api_key:
        # 没有密钥时登录、会话都能用，只有发消息会失败；启动时就说清楚。
        logger.error(
            "未配置 LLM_API_KEY（LLM_PROVIDER=deepseek 时可改用 DEEPSEEK_API_KEY）："
            "发送消息将失败。请复制 backend/.env.example 为 backend/.env 并填写密钥。"
        )
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
