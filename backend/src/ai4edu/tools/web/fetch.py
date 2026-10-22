"""`web_fetch`：老师读取一个网页的正文（Markdown），结果只有模型可见。

工具只做参数校验与正文截断；真正的抓取由 `ToolContext.web` 注入的
`WebTools` 完成。网页正文不进入 `display`，学生看不到。

对应 `docs/architecture.md` 第 5 节（联网工具）。
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from ai4edu.tools.base import BaseTool, ToolContext, ToolResult
from ai4edu.utils.errors import WebToolsError

_MAX_URL_LENGTH = 8192
_MAX_CONTENT_LENGTH = 20_000


def _invalid(ctx: ToolContext, reason: str) -> ToolResult:
    return ToolResult(
        content=ctx.reminders.text(
            "bad_tool_arguments", error=reason, name=WebFetchTool.name
        ),
        is_error=True,
        status_label="链接不对",
    )


class WebFetchTool(BaseTool):
    name = "web_fetch"
    description = (
        "读取一个网页的正文（Markdown）。搜索结果摘要不够、需要完整内容时"
        "抓取其中一两个链接。结果只有你可见。"
    )
    running_label = "正在读网页…"
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "要抓取的网页链接，必须是 http/https",
                "minLength": 1,
                "maxLength": 8192,
            },
        },
        "required": ["url"],
        "additionalProperties": False,
    }

    async def execute(
        self, input: dict[str, Any], ctx: ToolContext
    ) -> ToolResult:
        raw_url = input.get("url")
        if not isinstance(raw_url, str):
            return _invalid(ctx, "url 必须是字符串")
        url = raw_url.strip()
        if not url:
            return _invalid(ctx, "url 不能为空")
        if len(url) > _MAX_URL_LENGTH:
            return _invalid(ctx, f"url 不能超过 {_MAX_URL_LENGTH} 个字符")

        try:
            parsed = urlparse(url)
        except ValueError:
            return _invalid(ctx, "url 格式不正确")
        if parsed.scheme not in ("http", "https"):
            return _invalid(ctx, "url 只能使用 http 或 https")
        if not parsed.hostname:
            return _invalid(ctx, "url 缺少主机名")
        if parsed.username is not None or parsed.password is not None:
            return _invalid(ctx, "url 不能包含用户名或密码")

        if ctx.web is None:
            return ToolResult(
                content=ctx.reminders.text("web_tools_unavailable"),
                is_error=True,
                status_label="查资料未开通",
            )

        try:
            page = await ctx.web.fetch(url)
        except WebToolsError as exc:
            return ToolResult(
                content=ctx.reminders.text("web_fetch_failed", error=str(exc)),
                is_error=True,
                status_label="读网页失败",
            )

        body = page.content
        if len(body) > _MAX_CONTENT_LENGTH:
            body = (
                body[:_MAX_CONTENT_LENGTH]
                + "\n\n……\n\n（正文过长，已截断）"
            )
        content = (
            f"已读取网页「{page.title}」（只有老师可见）：\n\n{body}"
            "\n\n"
            + ctx.reminders.text("after_web_fetch")
        )
        return ToolResult(content=content, status_label="网页读好了")


web_fetch = WebFetchTool()
