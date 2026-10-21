"""辅导业务钩子：把散落在循环里的业务规则集中到一处。

实现 `core.query_loop.LoopHooks`：
- 守卫（空步追加提醒重试、超限报错）；
- 本回合 `analyze_problem` 成功后，后续步骤的工具列表去掉 `record_diagnosis`；
- 本步已有正文下发且有工具调用时，下一步追加“已经对学生说过”的提醒；
- 消息持久化（写 `messages` 表、更新 `last_assistant_message_id`）；
- 每步的工具列表来自 `registry.available_for(phase, 本回合已成功的工具)`
  （phase 每步重新读取 `ctx.state`，上一步工具可能刚改过它）；工具冲突
  （如分析完不诊断）由工具的 `unavailable_after` 声明、注册表执行，
  本模块不写具体工具名；
- 按步骤决定 thinking 与 tool_choice（`docs/architecture.md` 3.2）。
"""

from __future__ import annotations

from dataclasses import dataclass

from ai4edu.models.contracts import ThinkingMode, ToolChoice
from ai4edu.core.query_loop import StepDecision, StepPlan
from ai4edu.hooks.guard import TurnGuard
from ai4edu.models.content import TextBlock
from ai4edu.models.messages import Message
from ai4edu.prompts.reminders import Reminders
from ai4edu.tools.base import ToolContext
from ai4edu.tools.registry import ToolRegistry, to_tool_schemas

# 只写回复的步骤也保持 auto：提示词里已经要求只写回复。
_TOOL_CHOICE: ToolChoice = "auto"


@dataclass(frozen=True)
class TurnFacts:
    """决定本步 thinking/tool_choice 需要的回合事实。"""

    step: int
    has_diagnosis: bool  # 本回合已有一次成功的 record_diagnosis
    has_analyze: bool  # 本回合已有一次成功的 analyze_problem
    last_step_tool_error: bool  # 上一个工具结果是错误
    has_figure: bool = False  # 本回合已成功打开一次图


def choose_step_mode(facts: TurnFacts) -> tuple[ThinkingMode, ToolChoice]:
    """按 `docs/architecture.md` 3.2 决定本步是否思考。

    第一步要判断意图、写诊断，开思考；本回合已经诊断/分析/画图成功（判断已
    做完、只剩写回复）后关思考（实测 28–33 秒降到 2.5–4 秒）；其余情况
    （如工具报错后需要模型修正重试）保持开思考。
    """

    if facts.step <= 1:
        return "on", _TOOL_CHOICE
    if facts.has_diagnosis or facts.has_analyze or facts.has_figure:
        return "off", _TOOL_CHOICE
    return "on", _TOOL_CHOICE


class TutoringHooks:
    """一个学生回合内的业务规则与持久化。"""

    def __init__(
        self,
        *,
        ctx: ToolContext,
        guard: TurnGuard,
        reminders: Reminders,
        registry: ToolRegistry,
    ) -> None:
        self._ctx = ctx
        self._guard = guard
        self._reminders = reminders
        self._registry = registry
        self._succeeded: set[str] = set()
        self._diagnosed = False
        self._analyzed = False
        self._drew_figure = False
        self._last_tool_error = False

    def before_step(self, step: int) -> StepPlan:
        tools = self._registry.available_for(
            self._ctx.state.phase, succeeded=self._succeeded
        )
        thinking, tool_choice = choose_step_mode(
            TurnFacts(
                step=step,
                has_diagnosis=self._diagnosed,
                has_analyze=self._analyzed,
                has_figure=self._drew_figure,
                last_step_tool_error=self._last_tool_error,
            )
        )
        return StepPlan(
            tools=to_tool_schemas(tools),
            thinking=thinking,
            tool_choice=tool_choice,
        )

    async def on_message(self, message: Message) -> None:
        if message.turn_id is None and message.role != "user":
            # 回合内生成的 assistant/tool 消息补上回合号；提醒不持久化，
            # 不会走到这里。
            message.turn_id = self._ctx.turn_id
        rows = await self._ctx.store.append_messages([message])
        await self._ctx.store.commit()
        if message.role == "assistant":
            self._ctx.last_assistant_message_id = rows[0].db_id

    def after_tool(self, name: str, *, is_error: bool) -> bool:
        self._last_tool_error = is_error
        if not is_error:
            self._succeeded.add(name)
            if name == "analyze_problem":
                self._analyzed = True
            elif name == "draw_figure":
                self._drew_figure = True
            elif name == "record_diagnosis":
                self._diagnosed = True
        return False

    def after_step(self, *, has_tool_calls: bool, sent_text: bool) -> StepDecision:
        decision = self._guard.finish_step(
            has_tool_calls=has_tool_calls, sent_text=sent_text
        )
        if decision.action == "error":
            return StepDecision("error", error_text=decision.error_message)
        if decision.action == "retry":
            return StepDecision(
                "retry",
                reminder=self._reminder_message(
                    decision.reminder or self._guard.reminder
                ),
            )
        if has_tool_calls and sent_text:
            # 本步已经有正文发给学生，下一步只允许补充，不允许重写。
            return StepDecision(
                "continue",
                reminder=self._reminder_message(
                    self._reminders.text("already_sent")
                ),
            )
        return StepDecision("continue")

    def _reminder_message(self, text: str) -> Message:
        return Message(role="user", content=[TextBlock(text=text)], turn_id=None)


__all__ = ["TurnFacts", "TutoringHooks", "choose_step_mode"]
