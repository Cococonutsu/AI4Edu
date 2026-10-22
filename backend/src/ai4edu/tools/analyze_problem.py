"""`analyze_problem`：接收老师拆好的题目模型，校验后开始辅导。

读题与拆题由辅导老师自己完成（规则在 `prompts/sections.py` 的"读题与拆题"段落），
本工具不调用任何模型：校验题目模型 → 存库 → 初始化辅导状态。校验失败时返回
具体字段原因，老师修正后重新调用。

对应 `docs/architecture.md` 第 5 节（工具）。
"""

from __future__ import annotations

import copy
import json
from typing import Any

from pydantic import ValidationError

from ai4edu.tools.base import BaseTool, ToolContext, ToolResult
from ai4edu.tools.record_diagnosis import inline_refs
from ai4edu.tutoring.policy import PolicyError, start_problem
from ai4edu.tutoring.problem import ProblemModel

_FIELD_DESCRIPTIONS: dict[str, str] = {
    "statement": "题目原文（从图片识别或学生输入），含选项。",
    "domain": "知识领域 id，取值见系统提示词的领域模板。",
    "givens": "题目明确给出的条件，不根据示意图外观补充。",
    "goal": "所求。",
    "answer": "最终答案；text 为文字，latex 可选。",
    "relations": "有序的关键关系，前提在前；id 用 R1、R2…。",
    "subtasks": "按解题顺序排列的子任务；必做 2–5 个，可追加一个 optional 的 extend 子任务；id 用 T1、T2…。",
    "reference_solution": "完整参考解法（学生不可见）。",
    "kind": "element、relation、justification、verification 或 generalization。",
    "depends_on": "依赖的关系 id，只能引用排在前面的关系。",
    "stage": "understand、represent、relate、solve、verify 或 extend。",
    "required_relations": "完成本子任务需要学生建立的关系 id，必做子任务至少一个。",
    "completion_criteria": "可观察的完成标准。",
    "optional": "是否为可选拓展子任务；extend 阶段必须为 true。",
}


def _annotate(node: Any) -> None:
    if isinstance(node, dict):
        for name, prop in (node.get("properties") or {}).items():
            if isinstance(prop, dict) and name in _FIELD_DESCRIPTIONS:
                prop.setdefault("description", _FIELD_DESCRIPTIONS[name])
        for value in node.values():
            _annotate(value)
    elif isinstance(node, list):
        for item in node:
            _annotate(item)


def problem_input_schema() -> dict[str, Any]:
    """由 `ProblemModel` 生成工具参数 schema；学段由账号决定，不让模型填写。"""

    schema = copy.deepcopy(ProblemModel.model_json_schema())
    schema.get("properties", {}).pop("grade_band", None)
    if "required" in schema:
        schema["required"] = [name for name in schema["required"] if name != "grade_band"]
    _annotate(schema)
    return inline_refs(schema)


def _validation_message(exc: ValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors()[:8]:
        location = ".".join(str(item) for item in error.get("loc", ()))
        message = str(error.get("msg"))
        parts.append(f"{location}: {message}" if location else message)
    return "；".join(parts) or str(exc)


class AnalyzeProblemTool(BaseTool):
    name = "analyze_problem"
    description = (
        "学生发来一道需要多步推理的完整题目（文字或图片）时调用。"
        "先按系统提示词的\"读题与拆题\"自己读题并拆解，把题目模型作为参数传入；"
        "系统据此开始辅导。返回后用一句话复述题目要求，然后围绕当前子任务提出第一个问题。"
    )
    running_label = "正在读题…"
    establishes = ("analyzed",)
    input_schema: dict[str, Any] = problem_input_schema()

    def is_concurrency_safe(self, input: dict[str, Any]) -> bool:
        # 写题目并初始化辅导状态，并行执行时会互相覆盖；将来引入并行
        # 编排时需独占（当前循环串行执行，无实际影响）。
        return False

    async def execute(self, input: dict[str, Any], ctx: ToolContext) -> ToolResult:
        reminders = ctx.reminders
        payload = dict(input)
        # 学段由学生账号决定，不依赖模型填写（模型常写成"初中"或漏填）。
        payload["grade_band"] = ctx.user.grade_band
        try:
            problem = ProblemModel.model_validate(payload)
            new_state_check = start_problem(problem, 0, ctx.config)
        except ValidationError as exc:
            return ToolResult(
                content=reminders.text(
                    "analyze_failed", error=_validation_message(exc)
                ),
                is_error=True,
                status_label="读题失败",
            )
        except PolicyError as exc:
            return ToolResult(
                content=reminders.text("analyze_failed", error=str(exc)),
                is_error=True,
                status_label="读题失败",
            )
        del new_state_check

        record = await ctx.store.add_problem(
            model_json=problem.model_dump(mode="json"),
            # 不做验算或复核；字段保留以兼容已有数据，固定写 unverified。
            confidence="unverified",
            framework_version=ctx.config.framework.version,
        )
        await ctx.store.commit()

        new_state = start_problem(problem, record.id, ctx.config)
        ctx.problem = problem
        await ctx.persist_state(new_state)

        result = {
            "problem_id": record.id,
            "statement": problem.statement,
            "goal": problem.goal,
            "subtasks": [
                {"id": subtask.id, "title": subtask.title, "goal": subtask.goal}
                for subtask in problem.subtasks
            ],
            "current_subtask_id": new_state.active_subtask_id,
            "instruction": reminders.text("after_analyze_confident"),
        }
        return ToolResult(
            content=json.dumps(result, ensure_ascii=False),
            status_label="题目分析完成",
        )


analyze_problem = AnalyzeProblemTool()
