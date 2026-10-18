"""智能体循环向外产出的事件。

学生端只会看到正文、思考状态、工具状态文字和回合状态；思考文本本身、
工具参数与结果都不在这些事件里。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

TurnStatus = Literal["complete", "stopped", "error"]
ToolState = Literal["running", "done", "error"]


@dataclass
class TurnStarted:
    turn_id: str


@dataclass
class TextDelta:
    text: str


@dataclass
class ThinkingState:
    active: bool


@dataclass
class ToolStatus:
    tool: str
    label: str
    state: ToolState


@dataclass
class TurnFinished:
    status: TurnStatus
    message_id: int | None = None


@dataclass
class AgentError:
    message: str


AgentEvent: TypeAlias = (
    TurnStarted | TextDelta | ThinkingState | ToolStatus | TurnFinished | AgentError
)
