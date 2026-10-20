"""智能体事件 → NDJSON；以及同一会话的运行任务登记与取消。"""

from __future__ import annotations

import asyncio
from typing import Any

from ai4edu.core.events import (
    AgentError,
    AgentEvent,
    TextDelta,
    ThinkingState,
    ToolDisplay,
    ToolStatus,
    TurnFinished,
    TurnStarted,
)


class RunRegistry:
    """`conversation_id → 正在运行的生成任务`。"""

    def __init__(self) -> None:
        self._runs: dict[int, asyncio.Task[Any]] = {}

    def is_running(self, conversation_id: int) -> bool:
        task = self._runs.get(conversation_id)
        return task is not None and not task.done()

    def start(self, conversation_id: int, task: asyncio.Task[Any]) -> bool:
        if self.is_running(conversation_id):
            return False
        self._runs[conversation_id] = task
        return True

    def finish(self, conversation_id: int, task: asyncio.Task[Any]) -> None:
        if self._runs.get(conversation_id) is task:
            self._runs.pop(conversation_id, None)

    def cancel(self, conversation_id: int) -> bool:
        task = self._runs.get(conversation_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True


runs = RunRegistry()


def event_to_json(event: AgentEvent) -> dict[str, Any]:
    """字段严格对应 `docs/architecture.md` 第 8 节的 NDJSON 事件表。"""

    if isinstance(event, TurnStarted):
        return {
            "type": "turn_started",
            "turn_id": event.turn_id,
            "phase": event.phase,
        }
    if isinstance(event, TextDelta):
        return {"type": "text_delta", "text": event.text}
    if isinstance(event, ThinkingState):
        return {"type": "thinking", "active": event.active}
    if isinstance(event, ToolDisplay):
        return {"type": "display", "kind": event.kind, "payload": event.payload}
    if isinstance(event, ToolStatus):
        return {
            "type": "tool_status",
            "tool": event.tool,
            "label": event.label,
            "state": event.state,
        }
    if isinstance(event, TurnFinished):
        return {
            "type": "turn_finished",
            "status": event.status,
            "message_id": event.message_id,
        }
    if isinstance(event, AgentError):
        return {"type": "error", "message": event.message}
    raise TypeError(f"未知智能体事件：{type(event)!r}")
