"""按配置创建 Provider 与 OpenAI 兼容客户端。"""

from __future__ import annotations

from openai import AsyncOpenAI

from ai4edu.api.base import Provider
from ai4edu.api.glm import GLMProvider
from ai4edu.config import Settings

_KNOWN_PROVIDERS = ("glm",)


def make_client(settings: Settings) -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
    )


def make_provider(
    settings: Settings, client: AsyncOpenAI | None = None
) -> Provider:
    """按 `settings.llm_provider` 选择厂商；换模型厂商只改环境变量。"""

    if settings.llm_provider not in _KNOWN_PROVIDERS:
        raise ValueError(
            f"未知的 LLM_PROVIDER {settings.llm_provider!r}；"
            f"可用：{'、'.join(_KNOWN_PROVIDERS)}"
        )
    return GLMProvider(client or make_client(settings))


__all__ = ["make_client", "make_provider"]
