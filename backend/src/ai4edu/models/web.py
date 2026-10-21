"""联网工具的数据契约：`api/` 实现，`tools/` 消费。

只依赖标准库，不导入本项目的其他子包。工具层只认这里的结构，不关心
搜索与抓取由哪个厂商、通过什么 HTTP 端点完成。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


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
    """联网搜索与网页抓取。`api/` 提供实现，`tools/` 通过 `ToolContext` 消费。"""

    async def search(self, query: str, *, count: int = 5) -> list[WebSearchHit]: ...

    async def fetch(self, url: str) -> WebFetchPage: ...


__all__ = ["WebFetchPage", "WebSearchHit", "WebTools", "WebToolsError"]
