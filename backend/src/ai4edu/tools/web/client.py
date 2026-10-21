"""联网工具的契约与默认实现（DeepSeek 的搜索/抓取 HTTP 端点）。

`web_search` / `web_fetch` 只做参数校验与结果排版，真正联网的是本文件的
`DeepSeekWebTools`：拼端点、带鉴权、解析响应、把网络与 HTTP 错误统一映射成
`WebToolsError(recoverable)`。`WebTools` 协议是注入边界（`ToolContext.web`）：
测试用假件替换；将来换搜索服务商，只改本文件的实现，工具不动。这里不做
自动重试，错误原样交给工具层回给模型。

对应 `docs/architecture.md` 第 5 节（联网工具）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from ai4edu.config import Settings

# 限流、超时与服务端错误可以稍后重试；其余 4xx 是请求本身的问题。
_RECOVERABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


# ---- 契约（工具层只认这些结构，不关心实现） ----


@dataclass
class WebSearchHit:
    """一条联网搜索结果。

    `snippet` 是短摘要，`summary` 是给模型读的长摘要；`site_name` 与 `date`
    可能缺失（厂商返回 null）。`rerank_score` 取值 0–3，`authority` 取值 -1–4，
    都只作为模型判断可信度的参考。
    """

    title: str
    url: str
    snippet: str
    summary: str
    site_name: str | None
    date: str | None
    rerank_score: float
    authority: int


@dataclass
class WebFetchPage:
    """抓取到的网页正文（Markdown）。"""

    title: str
    content: str


class WebToolsError(Exception):
    """联网工具调用失败。

    `recoverable` 表示同类请求稍后重试是否可能成功（限流、超时、服务端
    5xx 为真；余额不足、参数错误等为假）。工具层不自动重试，把原因原样
    回给模型。
    """

    def __init__(self, message: str, *, recoverable: bool) -> None:
        super().__init__(message)
        self.recoverable = recoverable


class WebTools(Protocol):
    """联网搜索与网页抓取；生产实现是本文件的 `DeepSeekWebTools`。"""

    async def search(self, query: str, *, count: int = 5) -> list[WebSearchHit]: ...

    async def fetch(self, url: str) -> WebFetchPage: ...


# ---- 默认实现：DeepSeek 的 /v1/tools/search 与 /v1/tools/fetch ----


def _normalize_base_url(base_url: str) -> str:
    """去掉末尾的 `/`；用户若把 base 写到 `/v1`，也去掉，统一由下面拼端点。"""

    normalized = base_url.strip().rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[: -len("/v1")]
    return normalized


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class DeepSeekWebTools:
    """通过 DeepSeek 的联网工具端点执行搜索与抓取。"""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.deepseek.com",
        timeout_search: float = 15.0,
        timeout_fetch: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        base = _normalize_base_url(base_url)
        self._api_key = api_key
        self._search_url = f"{base}/v1/tools/search"
        self._fetch_url = f"{base}/v1/tools/fetch"
        self._timeout_search = timeout_search
        self._timeout_fetch = timeout_fetch
        # 测试注入 httpx.MockTransport；生产环境为 None，使用默认传输。
        self._transport = transport

    async def search(self, query: str, *, count: int = 5) -> list[WebSearchHit]:
        data = await self._post(
            self._search_url,
            {"query": query, "count": count},
            timeout=self._timeout_search,
        )
        results = data.get("results")
        if not isinstance(results, list):
            return []

        hits: list[WebSearchHit] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            hits.append(
                WebSearchHit(
                    title=str(item.get("title") or ""),
                    url=str(item.get("url") or ""),
                    snippet=str(item.get("snippet") or ""),
                    summary=str(item.get("summary") or ""),
                    site_name=_optional_str(item.get("site_name")),
                    date=_optional_str(item.get("date")),
                    rerank_score=_as_float(item.get("rerank_score")),
                    authority=_as_int(item.get("authority")),
                )
            )
        return hits

    async def fetch(self, url: str) -> WebFetchPage:
        data = await self._post(
            self._fetch_url, {"url": url}, timeout=self._timeout_fetch
        )
        return WebFetchPage(
            title=str(data.get("title") or ""),
            content=str(data.get("content") or ""),
        )

    async def _post(
        self, url: str, payload: dict[str, Any], *, timeout: float
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=timeout,
                transport=self._transport,
            ) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise WebToolsError(
                f"网络错误：请求超时（{exc}）", recoverable=True
            ) from exc
        except httpx.TransportError as exc:
            raise WebToolsError(f"网络错误：{exc}", recoverable=True) from exc
        except httpx.HTTPStatusError as exc:
            raise self._status_error(exc) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise WebToolsError(
                "联网服务返回的不是合法 JSON", recoverable=True
            ) from exc
        if not isinstance(data, dict):
            raise WebToolsError(
                "联网服务返回的数据格式不正确", recoverable=True
            )
        return data

    @staticmethod
    def _error_detail(response: httpx.Response) -> str | None:
        """尝试从 OpenAI 兼容错误体里取 `error.message`。"""

        try:
            data = response.json()
        except ValueError:
            return None
        if not isinstance(data, dict):
            return None
        error = data.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
        if isinstance(error, str) and error.strip():
            return error.strip()
        return None

    @classmethod
    def _status_error(cls, exc: httpx.HTTPStatusError) -> WebToolsError:
        status = exc.response.status_code
        detail = cls._error_detail(exc.response)
        if status == 402:
            return WebToolsError(
                f"账户余额不足：{detail or '请检查 DeepSeek 账户余额'}",
                recoverable=False,
            )
        message = detail or f"联网服务返回 HTTP {status}"
        return WebToolsError(
            message, recoverable=status in _RECOVERABLE_STATUS
        )


def make_web_tools(settings: Settings) -> DeepSeekWebTools | None:
    """按配置创建联网工具；未配置 `deepseek_api_key` 时不启用。"""

    if not settings.deepseek_api_key.strip():
        return None
    return DeepSeekWebTools(
        settings.deepseek_api_key, base_url=settings.deepseek_base_url
    )


__all__ = [
    "DeepSeekWebTools",
    "WebFetchPage",
    "WebSearchHit",
    "WebTools",
    "WebToolsError",
    "make_web_tools",
]
