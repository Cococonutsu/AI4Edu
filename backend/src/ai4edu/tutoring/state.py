"""辅导状态与等级比较工具。

状态保存在 `conversations.state_json`，由本模块的 Pydantic 模型定义结构。
所有函数只做纯数据处理。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .decision import Decision
from .diagnosis import Gap


class Phase(StrEnum):
    """会话阶段。"""

    idle = "idle"
    tutoring = "tutoring"
    completed = "completed"
    extension = "extension"


class SoloLevel(StrEnum):
    """SOLO 结构层次；SU 表示证据不足，不属于 SOLO 层次。"""

    S0 = "S0"
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"
    SU = "SU"


class SupportLevel(StrEnum):
    """支持等级。v1 规则引擎最多到 L3，L4 保留给教师介入。"""

    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"


class MathStatus(StrEnum):
    """数学正误，与结构层次、完成状态分别判断。"""

    unverified = "unverified"
    correct = "correct"
    nonblocking_error = "nonblocking_error"
    blocking_error = "blocking_error"


class SubtaskStatus(StrEnum):
    pending = "pending"
    active = "active"
    completed = "completed"


class SubtaskState(BaseModel):
    """单个子任务的运行时状态。"""

    subtask_id: str
    status: SubtaskStatus = SubtaskStatus.pending
    solo_level: SoloLevel | None = None
    independent_level: SoloLevel | None = None
    math_status: MathStatus = MathStatus.unverified
    established: list[str] = Field(default_factory=list)
    missing: list[Gap] = Field(default_factory=list)
    support_level: SupportLevel = SupportLevel.L0
    # 规则引擎允许的最高支持等级。同一子任务内只升不降，换子任务重新开始。
    allowed_support: SupportLevel | None = None
    stuck_turns: int = 0
    turns: int = 0


class TutorState(BaseModel):
    """一道题的完整辅导状态。"""

    phase: Phase = Phase.idle
    problem_id: int | None = None
    active_subtask_id: str | None = None
    subtasks: dict[str, SubtaskState] = Field(default_factory=dict)
    last_decision: Decision | None = None
    framework_version: str | None = None
    # 同一道题中"只报答案求对错"（probe）的累计次数；换新题时归零。
    answer_probes: int = 0

    @classmethod
    def idle(cls) -> "TutorState":
        return cls(phase=Phase.idle)

    def to_json(self) -> dict[str, Any]:
        """转成可写入 `state_json` 的普通字典（枚举转字符串）。"""

        return self.model_dump(mode="json")

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "TutorState":
        """从 `state_json` 还原状态。"""

        return cls.model_validate(data)


_SOLO_ORDER: tuple[SoloLevel, ...] = (
    SoloLevel.S0,
    SoloLevel.S1,
    SoloLevel.S2,
    SoloLevel.S3,
    SoloLevel.S4,
)
_SUPPORT_ORDER: tuple[SupportLevel, ...] = (
    SupportLevel.L0,
    SupportLevel.L1,
    SupportLevel.L2,
    SupportLevel.L3,
    SupportLevel.L4,
)


def _coerce_solo(level: SoloLevel | str) -> SoloLevel:
    if isinstance(level, SoloLevel):
        return level
    try:
        return SoloLevel(level)
    except ValueError as exc:
        raise ValueError(f"未知的 SOLO 层次：{level!r}") from exc


def solo_rank(level: SoloLevel | str | None) -> int | None:
    """S0–S4 → 0–4；SU 或 None 不参与比较，返回 None。"""

    if level is None:
        return None
    solo_level = _coerce_solo(level)
    if solo_level is SoloLevel.SU:
        return None
    return _SOLO_ORDER.index(solo_level)


def support_rank(level: SupportLevel | str) -> int:
    """L0–L4 → 0–4。"""

    try:
        support_level = level if isinstance(level, SupportLevel) else SupportLevel(level)
    except ValueError as exc:
        raise ValueError(f"未知的支持等级：{level!r}") from exc
    return _SUPPORT_ORDER.index(support_level)


def raise_support(
    level: SupportLevel | str, steps: int, cap: SupportLevel | str
) -> SupportLevel:
    """把支持等级提高 `steps` 级，不超过 `cap`；不会降低已有等级。"""

    current = support_rank(level)
    ceiling = support_rank(cap)
    if ceiling < current:
        ceiling = current
    target = min(current + max(steps, 0), ceiling)
    return _SUPPORT_ORDER[target]
