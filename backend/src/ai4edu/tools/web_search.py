"""`web_search`：老师联网搜索，结果只有模型可见。

工具只做参数校验与结果排版；真正的搜索由 `ToolContext.web` 注入的
`WebTools` 完成（`api/deepseek_tools.py` 是生产实现）。搜索结果不进入
`display`，学生看不到。
"""

from __future__ import annotations

from typing import Any

from ai4edu.models.web import WebSearchHit, WebToolsError
from ai4edu.tools.base import BaseTool, ToolContext, ToolResult

_MAX_QUERY_LENGTH = 128
_DEFAULT_COUNT = 5
_MIN_COUNT = 1
_MAX_COUNT = 10


def _invalid(ctx: ToolContext, reason: str) -> ToolResult:
    return ToolResult(
        content=ctx.reminders.text(
            "bad_tool_arguments", error=reason, name=WebSearchTool.name
        ),
        is_error=True,
        status_label="搜索失败",
    )


def _format_hit(index: int, hit: WebSearchHit) -> str:
    site_name = hit.site_name or "未知站点"
    date = hit.date or "日期未知"
    return "\n".join(
        [
            f"{index}. {hit.title}（{site_name}，{date}）",
            f"  链接：{hit.url}",
            f"  摘要：{hit.summary}",
            f"  （相关度 {hit.rerank_score:.1f}/3，权威度 {hit.authority}/4）",
        ]
    )


class WebSearchTool(BaseTool):
    name = "web_search"
    description = (
        "联网搜索，核实事实或查课本外的真实世界信息（年份、时事、数据等）。"
        "结果只有你可见。课本内的数学知识与计算不要搜索，自己完成。"
    )
    running_label = "正在联网搜索"
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词，短而具体；不是整道题",
                "minLength": 1,
                "maxLength": 128,
            },
            "count": {
                "type": "integer",
                "description": "想要的结果条数",
                "minimum": 1,
                "maximum": 10,
                "default": 5,
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    async def execute(
        self, input: dict[str, Any], ctx: ToolContext
    ) -> ToolResult:
        raw_query = input.get("query")
        if not isinstance(raw_query, str):
            return _invalid(ctx, "query 必须是字符串")
        query = raw_query.strip()
        if not query:
            return _invalid(ctx, "query 不能为空")
        if len(query) > _MAX_QUERY_LENGTH:
            return _invalid(ctx, f"query 不能超过 {_MAX_QUERY_LENGTH} 个字符")

        raw_count = input.get("count", _DEFAULT_COUNT)
        if isinstance(raw_count, bool) or not isinstance(raw_count, int):
            return _invalid(ctx, "count 必须是整数")
        count = max(_MIN_COUNT, min(_MAX_COUNT, raw_count))

        if ctx.web is None:
            return ToolResult(
                content=ctx.reminders.text("web_tools_unavailable"),
                is_error=True,
                status_label="联网搜索不可用",
            )

        try:
            hits = await ctx.web.search(query, count=count)
        except WebToolsError as exc:
            return ToolResult(
                content=ctx.reminders.text("web_search_failed", error=str(exc)),
                is_error=True,
                status_label="联网搜索失败",
            )

        if not hits:
            return ToolResult(
                content=(
                    f"联网搜索「{query}」没有找到相关结果。"
                    "可以换更短、更具体的关键词重试，或基于课本知识继续辅导。"
                ),
                status_label="没有找到结果",
            )

        blocks = [
            f"联网搜索「{query}」完成，共 {len(hits)} 条结果（只有老师可见）：",
            "",
        ]
        for index, hit in enumerate(hits, start=1):
            blocks.append(_format_hit(index, hit))
            if index < len(hits):
                blocks.append("")
        content = "\n".join(blocks) + "\n\n" + ctx.reminders.text(
            "after_web_search"
        )
        return ToolResult(
            content=content,
            status_label=f"已搜索到 {len(hits)} 条结果",
        )


web_search = WebSearchTool()
