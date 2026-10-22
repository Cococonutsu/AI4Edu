# ai4edu/

后端 Python 包。每个子目录一个职责，依赖方向见 `docs/architecture.md` 2.1
（`server → core → {api, models, prompts, session, hooks, tools} → tutoring → storage`）。
各子目录的 `AGENTS.md` 说明文件和边界；`server/routes/`、`storage/repos/`
由上一级的 `AGENTS.md` 覆盖。

| 路径 | 职责 |
|---|---|
| `config.py` | `Settings`：环境变量、数据与配置目录 |
| `server/` | HTTP 路由、NDJSON 流、学生可见消息过滤 |
| `auth/` | 密码、登录会话、当前用户 |
| `storage/` | ORM 模型与数据访问 |
| `api/` | Provider 协议与智谱实现：内部消息 ⇄ 厂商格式、流解析、异常映射 |
| `core/` | 智能体运行时：事件、无状态 query_loop、组装一切的 query_engine |
| `models/` | 内部数据结构：内容块、消息、序列规范化、请求契约类型 |
| `prompts/` | 所有给模型看的文字的唯一出口：段落文字（Python 常量）、按序组装、回合内短文字 |
| `session/` | 回合持久化编排（TurnStore）与历史修复（recovery） |
| `hooks/` | 注入循环的业务规则：回合守卫、辅导钩子、按步开关思考 |
| `tools/` | analyze_problem、record_diagnosis、draw_figure |
| `tutoring/` | 状态机与规则引擎（纯逻辑） |
| `cli/` | 管理员命令行 |
