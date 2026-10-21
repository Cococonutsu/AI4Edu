"""按配置创建 Provider 与 OpenAI 兼容客户端。"""

from __future__ import annotations

from openai import AsyncOpenAI

from ai4edu.api.base import Provider
from ai4edu.api.deepseek import DeepSeekProvider
from ai4edu.api.glm import GLMProvider
from ai4edu.api.openai_compat import OpenAICompatProvider
from ai4edu.config import Settings

_KNOWN_PROVIDERS = ("glm", "deepseek")

_DEFAULT_BASE_URLS = {
    "glm": "https://open.bigmodel.cn/api/paas/v4",
    "deepseek": "https://api.deepseek.com",
}

_PROVIDER_CLASSES: dict[str, type[OpenAICompatProvider]] = {
    "glm": GLMProvider,
    "deepseek": DeepSeekProvider,
}


def _require_known_provider(provider: str) -> str:
    if provider not in _KNOWN_PROVIDERS:
        raise ValueError(
            f"未知的 LLM_PROVIDER {provider!r}；"
            f"可用：{'、'.join(_KNOWN_PROVIDERS)}"
        )
    return provider


def llm_credentials(settings: Settings) -> tuple[str, str]:
    """返回 `(base_url, api_key)`；留空的配置按厂商取默认值。

    `llm_base_url` 为空时用该厂商的默认地址（deepseek 取
    `deepseek_base_url`，与联网工具共用同一地址配置）；`llm_api_key`
    为空时，provider=deepseek 回退到 `deepseek_api_key`（联网工具也用
    这把 key），其他厂商没有回退值。
    """

    provider = _require_known_provider(settings.llm_provider)
    base_url = settings.llm_base_url
    if not base_url and provider == "deepseek":
        base_url = settings.deepseek_base_url
    if not base_url:
        base_url = _DEFAULT_BASE_URLS[provider]
    api_key = settings.llm_api_key
    if not api_key and provider == "deepseek":
        api_key = settings.deepseek_api_key
    return base_url, api_key


def make_client(settings: Settings) -> AsyncOpenAI:
    base_url, api_key = llm_credentials(settings)
    return AsyncOpenAI(base_url=base_url, api_key=api_key)


def make_provider(
    settings: Settings, client: AsyncOpenAI | None = None
) -> Provider:
    """按 `settings.llm_provider` 选择厂商；换模型厂商只改环境变量。"""

    provider = _require_known_provider(settings.llm_provider)
    provider_class = _PROVIDER_CLASSES[provider]
    return provider_class(client or make_client(settings))


__all__ = ["llm_credentials", "make_client", "make_provider"]
