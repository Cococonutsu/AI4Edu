# core/

智能体运行时。`query_engine.py` 组装一次回合的全部依赖（provider、工具、
消息、状态、hooks）并驱动循环；`query_loop.py` 是无状态的模型/工具循环；
`events.py` 定义模型层与回合层事件。不含辅导规则本身——规则来自
`hooks/` 与 `tutoring/`，通过注入作用于循环。

| 文件 | 内容 |
|---|---|
| `__init__.py` | 包导出（不 re-export `query_loop` 函数：与子模块同名会遮蔽模块属性） |
| `events.py` | 回合层事件（`TurnStarted`/`TextDelta`/`ThinkingState`/`ToolStatus`/`TurnFinished`/`AgentError`）；模型层事件从 `api/base.py` 转发 |
| `query_loop.py` | `query_loop()`：单回合内的多步模型/工具循环。只依赖 `models/`、`core/events.py` 与传入参数（AST 测试强制）；可恢复的 `ProviderError` 原步重试 2 次（1s、2s），已有正文下发时不重试；取消时已产生的思考与正文先落库 |
| `query_engine.py` | `QueryEngine`（原 TutorEngine）：校验归属、保存用户消息、加载历史/状态/题目/附件，构造 `TurnStore`/`ToolContext`/`TutoringHooks`/`ToolRunnerAdapter` 与每步重建系统提示词并记录 `llm_calls` 的 `call_model`；`LoopFailure.reason` 映射成学生可见错误 |

注意：`core/query_loop.py` 不得导入 `api/`、`storage/`、`tutoring/`、
`prompts/`、`tools/`、`session/`，源码中不出现具体工具名
（`tests/backend/test_layering.py` 用 AST 检查）。
