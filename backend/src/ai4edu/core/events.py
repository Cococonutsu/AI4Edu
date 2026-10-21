"""循环内外传递的事件类型。

模型层事件（`ModelEvent`，定义见 `ai4edu.models.contracts`）由 Provider 从
厂商流解析产出，只在本回合内消费；回合层事件（`AgentEvent`）是循环向服务器
产出的 NDJSON 事件来源。两层都有“正文增量”，因此用不同的类名
（`ModelTextDelta` / `TextDelta`）避免混淆。思考文本、工具参数与结果只保存
在消息里，不出现在回合事件中。

对应 `docs/architecture.md` 第 8 节（NDJSON 事件）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Literal, TypeAlias

# ---- 回合层事件（循环 → 服务器 → 浏览器） ----

TurnStatus = Literal["complete", "stopped", "error"]
ToolState = Literal["running", "done", "error"]


@dataclass
class TurnStarted:
    turn_id: str
    # 回合开始时学生所处的阶段（`idle`/`tutoring`/...），前端据此选择等待文案。
    phase: str = "idle"


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
class ToolDisplay:
    """工具产出的、允许下发给浏览器的展示数据（如 `draw_figure` 的图）。"""

    kind: str
    payload: dict[str, Any]


@dataclass
class TurnFinished:
    status: TurnStatus
    message_id: int | None = None


@dataclass
class AgentError:
    message: str


AgentEvent: TypeAlias = (
    TurnStarted
    | TextDelta
    | ThinkingState
    | ToolStatus
    | ToolDisplay
    | TurnFinished
    | AgentError
)

__all__ = [
    "AgentError",
    "AgentEvent",
    "TextDelta",
    "ThinkingState",
    "ToolDisplay",
    "ToolStatus",
    "TurnFinished",
    "TurnStarted",
]
