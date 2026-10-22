# tools/

模型可调用的工具。每个工具一个文件，继承 `base.BaseTool`，在 `registry.py` 注册；成组的工具按域放子包（目前只有 `web/`）。

约定：`input_schema` 是 JSON Schema；`execute(input, ctx)` 为异步，返回 `ToolResult{content: str(给模型看的文本/JSON), is_error: bool, status_label: str(给学生看的状态文字)}`。输入不合法时返回 `is_error=True` 并说明原因，让模型重填，不要抛异常。工具不调用模型。

`registry.py` 是工具的唯一登记处：所有工具实例、每个会话阶段可用哪些工具、按名字找执行体、转成发给模型的 `ToolSchema`，都从这里出。新增工具 = 新建工具文件 + 在这里登记一行；`hooks/`、`core/` 不写死工具名（AST 测试强制）。

| 文件 | 内容 |
|---|---|
| `__init__.py` | 包标记 |
| `base.py` | `BaseTool`（`execute` 异步、`is_concurrency_safe` 并发安全声明）、`ToolResult`（`content` 为 `ToolResultContent`）、`ToolContext`：工具真正需要的最小上下文——`store` 持久化与 `persist_state`、`config`/`reminders`、`user`（StudentProfile 领域视图，不持 ORM）、会话标识、`state`/`problem`、`web`；模型调用日志在 `TurnStore`（session 组件），不在工具上下文 |
| `registry.py` | `ToolRegistry`（运行时对象，对齐 cc）：`register`（重名报错）、`get`、`available_for(phase, succeeded)`（阶段过滤 + 工具用 `unavailable_after` 声明的回合内冲突）、`to_tool_schemas`；`build_registry()` 默认工具集，由 query_engine 装配、测试可注入子集 |
| `analyze_problem.py` | 接收老师按"读题与拆题"拆好的题目模型（工具参数），校验、存库、初始化辅导状态；不调用模型，学段由账号填写 |
| `figure.py` | `draw_figure`：校验结构化图形描述（字段、数量、算式字符与名称白名单），把图作为 `ToolResult.display` 下发给浏览器；不执行模型给的代码 |
| `record_diagnosis.py` | 校验证据原文、写证据记录、调用规则引擎、返回决策 |
| `web/` | 联网工具子包：`search.py`（`web_search`）、`fetch.py`（`web_fetch`）、`client.py`（`WebTools` 契约与 DeepSeek HTTP 实现）。见 `web/AGENTS.md` |
