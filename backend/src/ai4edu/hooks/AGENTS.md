# hooks/

注入 `core/query_loop` 的业务规则。实现循环需要的 `LoopHooks` 协议：
守卫、工具过滤、提醒、持久化、按步开关思考。持久化经 `session/store`，
提醒文字来自 `prompts/reminders`。

| 文件 | 内容 |
|---|---|
| `__init__.py` | 包导出 |
| `guard.py` | `TurnGuard`：只处理空步——本回合还没有正文、这一步也没有工具调用时追加提醒重试，超限报错（文字从 `prompts.reminders` 注入）；正文一律即时下发 |
| `tutoring_hooks.py` | `TutoringHooks`：每步工具列表由 `registry.available_for(phase, 本回合已成功工具)` 给出（冲突由工具的 `unavailable_after` 声明，如分析完不诊断；本模块不写工具名）、正文已下发后的"不许重写"提醒、消息持久化；`choose_step_mode` 纯函数按回合事实决定 thinking/tool_choice（第 1 步开思考；诊断/分析完成后关思考；工具报错保持开思考） |
