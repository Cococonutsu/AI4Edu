"""回合守卫：辅导阶段必须先完成诊断，才能把正文发给学生。

守卫只缓冲“是否允许下发”的状态，不理解诊断内容。`loop.agent_loop` 在每一步
结束后调用 `finish_step()` 决定继续、追加提醒重试还是报错结束。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ai4edu.tutoring.state import Phase

GuardAction = Literal["continue", "retry", "error"]

_IDLE_REMINDER = (
    "（系统提醒：请先判断学生这条消息是完整题目还是点问题，"
    "调用 analyze_problem 或 answer_directly。）"
)
_TUTORING_REMINDER = (
    "（系统提醒：辅导进行中。请先调用 record_diagnosis 记录本轮诊断，再回复学生。）"
)
_GUARD_ERROR = "老师刚才走神了，请再发一次你的回答。"


@dataclass
class GuardDecision:
    action: GuardAction
    reminder: str | None = None
    error_message: str | None = None


class DiagnosisGuard:
    """一个学生回合内的守卫状态。"""

    def __init__(self, phase: Phase, retry_limit: int) -> None:
        self.phase = Phase(phase)
        self.mode: Literal["idle", "tutoring"] = (
            "idle" if self.phase is Phase.idle else "tutoring"
        )
        self.enabled = self.phase in (Phase.idle, Phase.tutoring, Phase.extension)
        self.retry_limit = max(int(retry_limit), 0)
        self.retries = 0
        self.unlocked = not self.enabled
        self._buffer: list[str] = []
        if self.mode == "idle":
            self._unlock_tools = frozenset({"analyze_problem", "answer_directly"})
        else:
            self._unlock_tools = frozenset(
                {"record_diagnosis", "answer_directly", "analyze_problem"}
            )

    @property
    def reminder(self) -> str:
        return _IDLE_REMINDER if self.mode == "idle" else _TUTORING_REMINDER

    def text_delta(self, text: str) -> bool:
        """记录一段正文增量；返回是否应立即下发给学生。"""

        if not self.enabled or self.unlocked:
            return True
        self._buffer.append(text)
        return False

    def buffered_text(self) -> str:
        return "".join(self._buffer)

    def discard_buffer(self) -> None:
        self._buffer.clear()

    def on_tool_result(self, name: str, is_error: bool) -> None:
        if not is_error and name in self._unlock_tools:
            self.unlocked = True

    def finish_step(self, *, has_tool_calls: bool) -> GuardDecision:
        """一步模型调用结束后的处理。

        有工具调用时丢弃缓冲正文并继续执行工具；没有工具调用且守卫仍未解除时
        丢弃正文并按次数重试，超过上限则报错。
        """

        self.discard_buffer()

        if not self.enabled or self.unlocked:
            return GuardDecision("continue")

        if has_tool_calls:
            return GuardDecision("continue")

        if self.retries >= self.retry_limit:
            return GuardDecision(
                "error",
                error_message=_GUARD_ERROR,
            )

        self.retries += 1
        return GuardDecision("retry", reminder=self.reminder)
