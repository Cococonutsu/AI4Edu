"""创建 OpenAI 兼容客户端。"""

from __future__ import annotations

from openai import AsyncOpenAI

from ai4edu.config import Settings


def make_client(settings: Settings) -> AsyncOpenAI:
    """按 `Settings` 创建异步客户端；密钥只来自环境或 `backend/.env`。"""

    return AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )
