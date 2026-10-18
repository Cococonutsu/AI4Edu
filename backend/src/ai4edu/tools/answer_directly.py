"""`answer_directly`：回答点问题、核对或非题目消息。

`reply` 是学生将看到的完整文字，工具确认后暂存在 `ctx.pending_reply`，
由引擎在模型没有另写正文时下发。工具不改变辅导状态。
"""

from __future__ import annotations

import json
from typing import Any

from ai4edu.storage.repos import evidence
from ai4edu.tools.base import BaseTool, ToolContext, ToolResult
from ai4edu.tutoring.state import Phase

_MAX_REPLY_LENGTH = 800
_JUDGEMENT_MARKERS = (
    "对",
    "正确",
    "不对",
    "错误",
    "错",
    "没错",
    "有误",
    "不正确",
    "✓",
    "✗",
)
_TUTORING_PHASES = (Phase.tutoring, Phase.extension)


class AnswerDirectlyTool(BaseTool):
    name = "answer_directly"
    description = (
        "回答不是整题辅导的消息：概念问题（concept）、核对对错（check）、"
        "直接索要结论（direct）或闲聊（chat）。reply 是学生将看到的完整回复"
        "（Markdown + LaTeX），回答后结束，不要重复内容。"
        "辅导中进行核对（check）时必须用 has_work 标明学生是否展示了过程；"
        "学生只报答案时应改用 record_diagnosis（answer_only=true）。"
    )
    running_label = "正在回答…"
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["concept", "check", "direct", "chat"],
                "description": "消息类型：概念、核对、直接索要或闲聊。",
            },
            "reply": {
                "type": "string",
                "maxLength": _MAX_REPLY_LENGTH,
                "description": "学生将看到的完整回复，使用 Markdown 与 LaTeX。",
            },
            "advance": {
                "type": "boolean",
                "description": "是否推进当前子任务；点问题与插问保持 false。",
                "default": False,
            },
            "has_work": {
                "type": "boolean",
                "description": (
                    "学生这条消息是否包含算式、步骤或理由；"
                    "只报答案或选项为 false。辅导中进行核对（kind=check）时必填。"
                ),
            },
        },
        "required": ["kind", "reply"],
    }

    async def execute(self, input: dict[str, Any], ctx: ToolContext) -> ToolResult:
        kind = input.get("kind")
        if kind not in ("concept", "check", "direct", "chat"):
            return ToolResult(
                content="kind 必须是 concept、check、direct 或 chat",
                is_error=True,
                status_label="回复失败",
            )

        if kind == "check" and Phase(ctx.state.phase) in _TUTORING_PHASES:
            has_work = input.get("has_work")
            if not isinstance(has_work, bool):
                return ToolResult(
                    content=(
                        "辅导进行中，核对类回复必须填写 has_work"
                        "（学生这条消息是否包含算式、步骤或理由），请重试。"
                    ),
                    is_error=True,
                    status_label="回复失败",
                )
            if not has_work:
                return ToolResult(
                    content=(
                        "辅导进行中，学生只报了答案。请改为调用 record_diagnosis"
                        "（answer_only=true），按返回的决策回复，不要判断对错。"
                    ),
                    is_error=True,
                    status_label="回复失败",
                )

        raw_reply = input.get("reply")
        reply = raw_reply.strip() if isinstance(raw_reply, str) else ""
        if not reply:
            return ToolResult(
                content="reply 不能为空",
                is_error=True,
                status_label="回复失败",
            )
        if len(reply) > _MAX_REPLY_LENGTH:
            return ToolResult(
                content=f"reply 不能超过 {_MAX_REPLY_LENGTH} 字，请精简后重试",
                is_error=True,
                status_label="回复失败",
            )
        if kind == "check" and not any(marker in reply for marker in _JUDGEMENT_MARKERS):
            return ToolResult(
                content="核对类回复必须明确说出对或错，请修改 reply 后重试",
                is_error=True,
                status_label="回复失败",
            )

        problem_id = ctx.state.problem_id if ctx.problem is not None else None
        await evidence.add(
            ctx.db,
            conversation_id=ctx.conversation_id,
            problem_id=problem_id,
            subtask_id=ctx.state.active_subtask_id,
            message_id=ctx.user_message_id,
            evidence_json={"kind": kind, "reply": reply},
            solo_level=None,
            math_status="unverified",
            support_level="L0",
            gaps_json=[],
            decision_json={"action": "answer_directly", "kind": kind},
        )
        await ctx.db.commit()

        ctx.pending_reply = reply
        content = json.dumps({"accepted": True, "delivered": True}, ensure_ascii=False)
        return ToolResult(
            content=(
                content
                + "\n回复已原样发送给学生。请立即结束本回合："
                "不要再输出任何正文、确认、寒暄或重复内容。"
            ),
            status_label="已回复",
        )


answer_directly = AnswerDirectlyTool()
