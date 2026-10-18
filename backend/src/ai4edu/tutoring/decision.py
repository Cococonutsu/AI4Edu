"""规则引擎输出：本轮给学生回复的决策。

单独成文件是为了让 `state.TutorState` 可以引用它而不会与 `policy` 形成循环导入。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PhaseName = Literal["idle", "tutoring", "completed", "extension"]
SupportLevelName = Literal["L0", "L1", "L2", "L3", "L4"]


class Decision(BaseModel):
    """一轮诊断之后，辅导老师应当执行的动作与约束。"""

    action: str
    action_name: str
    guidance: str
    phase: PhaseName
    subtask_id: str | None = None
    subtask_title: str | None = None
    subtask_goal: str | None = None
    target: str = ""
    target_relation_id: str | None = None
    max_support_level: SupportLevelName = "L0"
    must_not_reveal: list[str] = Field(default_factory=list)
    next_subtask_id: str | None = None
    next_subtask_title: str | None = None
    has_extension: bool = False
    notes: list[str] = Field(default_factory=list)
