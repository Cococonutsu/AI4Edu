"""`record_diagnosis`：校验诊断、写证据记录、调用规则引擎。对应 `docs/architecture.md` 第 5 节（工具）。"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from ai4edu.tools.base import BaseTool, ToolContext, ToolResult
from ai4edu.tutoring.diagnosis import Diagnosis, validate_against
from ai4edu.tutoring.policy import PolicyError, decide

_FIELD_DESCRIPTIONS: dict[str, str] = {
    "subtask_id": "当前诊断针对的子任务 id，必须是题目模型中的子任务（通常是当前进行中的子任务）。",
    "evidence_quotes": "学生本轮原文中的连续子串，逐字摘录，不得改写或补造。",
    "established_relations": "本轮依据学生原文确认已建立的关系 id。",
    "solo_level": "当前子任务的结构层次 S0–S4；证据不足时填 SU（不是 S0）。",
    "math_status": "数学正误：unverified、correct、nonblocking_error 或 blocking_error。",
    "errors": "学生解答中的数学错误；blocking=true 表示阻碍当前子任务继续。",
    "gaps": "当前子任务尚未建立的内容，按题目关系的前提顺序选择最靠前的一项。",
    "completion_met": "是否已达到当前子任务的完成标准。",
    "made_progress": "本轮是否取得实质进展；影响连续卡住计数与支持升级。",
    "student_requested_help": "学生是否明确表示不会、求助或要求提示。",
    "prior_support_level": "回看老师上一条回复，它对当前子任务实际提供的支持等级 L0–L3。",
    "answer_only": (
        "本轮只报出整道题的最终答案或选项，没有任何过程；"
        "报出某一步的中间结果不算"
    ),
    "rationale": "判定理由：说明学生原文证据如何支持该层次、数学正误与缺口。",
    "quote": "学生原文中的错误片段，可留空。",
    "description": "错误或缺口的具体说明。",
    "blocking": "该错误是否阻碍当前子任务继续。",
    "gap_type": "缺口类型：concept、element、relation、justification、verification 或 generalization。",
    "relation_id": "缺口对应的关系 id；没有具体关系时可以省略。",
}


def _annotate(schema: dict[str, Any]) -> None:
    for name, description in _FIELD_DESCRIPTIONS.items():
        definition = schema.get("properties", {}).get(name)
        if isinstance(definition, dict) and not definition.get("description"):
            definition["description"] = description
    for definition in (schema.get("$defs") or {}).values():
        if not isinstance(definition, dict):
            continue
        for name, description in _FIELD_DESCRIPTIONS.items():
            prop = definition.get("properties", {}).get(name)
            if isinstance(prop, dict) and not prop.get("description"):
                prop["description"] = description


def inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """把 `$defs` / `$ref` 递归内联，得到模型更容易遵守的扁平 schema。"""

    definitions = schema.get("$defs") or {}

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                name = ref.split("/")[-1]
                target = resolve(definitions.get(name, {}))
                merged = dict(target) if isinstance(target, dict) else {}
                for key, value in node.items():
                    if key != "$ref":
                        merged[key] = resolve(value)
                return merged
            return {key: resolve(value) for key, value in node.items() if key != "$defs"}
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    return resolve(schema)


def diagnosis_input_schema() -> dict[str, Any]:
    raw = Diagnosis.model_json_schema()
    _annotate(raw)
    return inline_refs(raw)


def _validation_message(exc: ValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors()[:6]:
        location = ".".join(str(item) for item in error.get("loc", ()))
        parts.append(f"{location}: {error.get('msg')}")
    return "；".join(parts) or str(exc)


class RecordDiagnosisTool(BaseTool):
    name = "record_diagnosis"
    description = (
        "记录本轮对学生当前子任务的诊断，并取得规则引擎给出的下一步动作。"
        "辅导进行中，学生每次回复后必须先调用本工具，再写回复。"
        "evidence_quotes 必须是学生本轮原文的连续子串。"
        "学生只报出整道题的最终答案或选项、没有任何过程时，"
        "填 answer_only=true，并按返回的决策回复。"
    )
    running_label = "正在理解你的思路…"
    input_schema = diagnosis_input_schema()
    # 本回合刚分析完新题时，学生还没有针对子任务作答，不能诊断；
    # 由 registry.available_for 依据本声明把本工具从列表里剔除。
    unavailable_after = ("analyze_problem",)
    establishes = ("diagnosed",)

    def is_concurrency_safe(self, input: dict[str, Any]) -> bool:
        # 写证据记录并推进辅导状态，并行执行时会互相覆盖；将来引入并行
        # 编排时需独占（当前循环串行执行，无实际影响）。
        return False

    async def execute(self, input: dict[str, Any], ctx: ToolContext) -> ToolResult:
        if ctx.problem is None:
            return ToolResult(
                content="当前没有正在辅导的题目，不能记录诊断；请先调用 analyze_problem。",
                is_error=True,
                status_label="诊断失败",
            )

        try:
            diagnosis = Diagnosis.model_validate(input)
        except ValidationError as exc:
            return ToolResult(
                content="诊断字段不合法：" + _validation_message(exc),
                is_error=True,
                status_label="诊断失败",
            )

        issues = validate_against(diagnosis, ctx.problem, ctx.student_text)
        if issues:
            return ToolResult(
                content="诊断未通过校验：" + "；".join(issues) + "。请修正后重新调用。",
                is_error=True,
                status_label="诊断失败",
            )

        try:
            new_state, decision = decide(
                ctx.state, ctx.problem, diagnosis, ctx.config
            )
        except PolicyError as exc:
            return ToolResult(
                content=f"诊断与当前辅导状态不一致：{exc}。请检查 subtask_id 后重试。",
                is_error=True,
                status_label="诊断失败",
            )

        await ctx.store.add_evidence(
            problem_id=ctx.state.problem_id,
            subtask_id=diagnosis.subtask_id,
            message_id=ctx.user_message_id,
            evidence_json=diagnosis.model_dump(mode="json"),
            solo_level=diagnosis.solo_level,
            math_status=diagnosis.math_status,
            support_level=diagnosis.prior_support_level,
            gaps_json=[gap.model_dump(mode="json") for gap in diagnosis.gaps],
            decision_json=decision.model_dump(mode="json"),
        )
        await ctx.store.commit()
        await ctx.persist_state(new_state)

        return ToolResult(
            content=json.dumps(decision.model_dump(mode="json"), ensure_ascii=False),
            status_label="好了",
        )


record_diagnosis = RecordDiagnosisTool()
