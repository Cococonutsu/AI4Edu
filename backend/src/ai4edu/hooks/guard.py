"""回合守卫：不让学生面对一个什么都没说的回合。

点问题、核对与闲聊由模型直接写正文回复，正文一律即时下发；守卫只处理
"空步"：本回合到目前为止还没有任何正文，这一步也没有工具调用（例如只有
思考就结束了）。这种情况追加提醒重试，超过上限报错。提示文字由
`prompts.reminders` 提供并经构造函数注入。

对应 `docs/architecture.md` 第 3 节（回合守卫）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

GuardAction = Literal["continue", "retry", "error"]


@dataclass
class GuardDecision:
    action: GuardAction
    reminder: str | None = None
    error_message: str | None = None


class TurnGuard:
    """一个学生回合内的守卫状态。"""

    def __init__(
        self,
        retry_limit: int,
        *,
        reminder: str,
        error_message: str,
    ) -> None:
        self.retry_limit = max(int(retry_limit), 0)
        self.retries = 0
        self.reminder = reminder
        self._error_message = error_message
        self._sent_text = False

    def finish_step(self, *, has_tool_calls: bool, sent_text: bool) -> GuardDecision:
        """一步模型调用结束后的处理：空步重试，否则继续。"""

        if sent_text:
            self._sent_text = True
        if has_tool_calls or self._sent_text:
            return GuardDecision("continue")

        if self.retries >= self.retry_limit:
            return GuardDecision("error", error_message=self._error_message)

        self.retries += 1
        return GuardDecision("retry", reminder=self.reminder)


__all__ = ["GuardDecision", "TurnGuard"]
