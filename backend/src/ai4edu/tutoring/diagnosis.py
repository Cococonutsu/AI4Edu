"""诊断输入 `Diagnosis` 及其与题目原文的一致性校验。

字段与含义见 `docs/tutoring-framework.md` 第 4 节。诊断只描述学生对**当前子任务**
已经表达的内容，不是能力标签。
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from .problem import ProblemModel

GapType = Literal[
    "concept", "element", "relation", "justification", "verification", "generalization"
]
SoloLevelName = Literal["S0", "S1", "S2", "S3", "S4", "SU"]
MathStatusName = Literal["unverified", "correct", "nonblocking_error", "blocking_error"]
SupportLevelName = Literal["L0", "L1", "L2", "L3"]

_WHITESPACE_RE = re.compile(r"\s+")


class DiagnosisError(BaseModel):
    """学生解答中的一处数学错误。`blocking=True` 表示它阻碍当前子任务继续。"""

    quote: str = ""
    description: str
    blocking: bool = False


class Gap(BaseModel):
    """当前子任务中尚未建立的一项内容。"""

    gap_type: GapType
    relation_id: str | None = None
    description: str


class Diagnosis(BaseModel):
    """一轮学生回复后的诊断记录。"""

    subtask_id: str
    evidence_quotes: list[str] = Field(default_factory=list)
    established_relations: list[str] = Field(default_factory=list)
    solo_level: SoloLevelName
    math_status: MathStatusName = "unverified"
    errors: list[DiagnosisError] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    completion_met: bool = False
    made_progress: bool = False
    student_requested_help: bool = False
    prior_support_level: SupportLevelName = "L0"
    answer_only: bool = Field(
        default=False,
        description=(
            "本轮只报出整道题的最终答案或选项，没有任何过程；"
            "报出某一步的中间结果不算"
        ),
    )
    rationale: str = ""


def _normalize(text: str) -> str:
    """统一全角/半角空白并压缩连续空白，用于原文子串比对。"""

    return _WHITESPACE_RE.sub(" ", text).strip()


def validate_against(
    diag: Diagnosis, problem: ProblemModel, student_text: str
) -> list[str]:
    """校验诊断是否自洽、是否忠实引用学生原文。

    返回问题列表；空列表表示通过。这里不修改 `diag`。
    """

    issues: list[str] = []
    relation_ids = {relation.id for relation in problem.relations}
    normalized_student = _normalize(student_text)

    for index, quote in enumerate(diag.evidence_quotes):
        normalized_quote = _normalize(quote)
        if not normalized_quote:
            issues.append(f"evidence_quotes[{index}] 为空")
            continue
        if normalized_quote not in normalized_student:
            issues.append(f"evidence_quotes[{index}] 不是学生本轮原文：{quote!r}")

    if diag.solo_level != "SU" and not diag.evidence_quotes:
        issues.append("solo_level 不是 SU 时必须至少给出一条 evidence_quote")

    for relation_id in diag.established_relations:
        if relation_id not in relation_ids:
            issues.append(f"established_relations 中的 {relation_id} 不在题目关系中")

    for index, gap in enumerate(diag.gaps):
        if gap.relation_id is not None and gap.relation_id not in relation_ids:
            issues.append(
                f"gaps[{index}].relation_id {gap.relation_id} 不在题目关系中"
            )

    if diag.math_status == "blocking_error" and not any(
        error.blocking for error in diag.errors
    ):
        issues.append(
            "math_status 为 blocking_error 时 errors 中至少要有一个 blocking=True"
        )

    return issues
