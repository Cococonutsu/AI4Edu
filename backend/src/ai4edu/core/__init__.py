"""智能体运行时：事件类型、无状态循环与回合引擎。

`core/query_loop.py` 只依赖 `models/`、`core/events.py` 和传入的参数；
组装依赖（provider、工具、消息、状态、hooks）是 `core/query_engine.py`
的职责。持久化经 `session/`，模型调用经 `api/`。
"""

from ai4edu.core.events import (
    AgentError,
    AgentEvent,
    TextDelta,
    ThinkingState,
    ToolStatus,
    TurnFinished,
    TurnStarted,
)
from ai4edu.core.query_engine import QueryEngine, QueryEngineError
from ai4edu.core.query_loop import (
    LoopFailure,
    LoopHooks,
    StepDecision,
    StepPlan,
    StepRequest,
    ToolOutcome,
    ToolRunner,
)
from ai4edu.models.contracts import (
    ModelEvent,
    ModelStreamEnd,
    ModelTextDelta,
    ModelThinkingDelta,
    ModelUsage,
    ToolUseReady,
)

# 注意：不要在包级 re-export `query_loop` 函数——它与子模块同名，
# re-export 会把 `ai4edu.core.query_loop` 属性从模块覆盖成函数。
# 需要 `query_loop` 时从 `ai4edu.core.query_loop` 导入。

__all__ = [
    "AgentError",
    "AgentEvent",
    "LoopFailure",
    "LoopHooks",
    "ModelEvent",
    "ModelStreamEnd",
    "ModelTextDelta",
    "ModelThinkingDelta",
    "ModelUsage",
    "QueryEngine",
    "QueryEngineError",
    "StepDecision",
    "StepPlan",
    "StepRequest",
    "TextDelta",
    "ThinkingState",
    "ToolOutcome",
    "ToolRunner",
    "ToolStatus",
    "ToolUseReady",
    "TurnFinished",
    "TurnStarted",
]
