"""智能体事件 → NDJSON；以及同一会话的运行任务登记与取消。对应 `docs/architecture.md` 第 8 节（NDJSON 事件与后台生成）。"""

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
    """`conversation_id → (user_id, 正在运行的生成任务)`。

    生成任务与浏览器连接解耦：学生切到别的对话、连接断开，任务照样跑完，
    结果按步存库；只有 `/stop` 才会取消。任务结束时自动从登记表移除。
    """

    def __init__(self) -> None:
        self._runs: dict[int, tuple[int, asyncio.Task[Any]]] = {}

    def is_running(self, conversation_id: int) -> bool:
        entry = self._runs.get(conversation_id)
        return entry is not None and not entry[1].done()

    def running_for_user(self, user_id: int) -> set[int]:
        """该学生当前正在生成的会话 id。"""

        return {
            conversation_id
            for conversation_id, (owner, task) in self._runs.items()
            if owner == user_id and not task.done()
        }

    def start(self, conversation_id: int, user_id: int, task: asyncio.Task[Any]) -> bool:
        if self.is_running(conversation_id):
            return False
        self._runs[conversation_id] = (user_id, task)
        task.add_done_callback(lambda done: self.finish(conversation_id, done))
        return True

    def finish(self, conversation_id: int, task: asyncio.Task[Any]) -> None:
        entry = self._runs.get(conversation_id)
        if entry is not None and entry[1] is task:
            self._runs.pop(conversation_id, None)

    def cancel(self, conversation_id: int) -> bool:
        entry = self._runs.get(conversation_id)
        if entry is None or entry[1].done():
            return False
        entry[1].cancel()
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
