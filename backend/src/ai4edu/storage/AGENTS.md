# storage/

数据库层：SQLAlchemy 2.0 异步 + SQLite（aiosqlite）。表结构见 `docs/architecture.md` 第 7 节。

边界：只做数据存取，不含业务判断。凡是会话、消息、附件的查询函数都要求传入 `user_id`。`evidence_records` 只追加。JSON 字段用 `JSON` 类型存 Pydantic 模型的 `model_dump(mode="json")`。

| 文件 | 内容 |
|---|---|
| `__init__.py` | 导出连接、ORM 模型与常用函数 |
| `db.py` | 引擎、`async_session` 工厂、`init_db()` 建表并对旧 `llm_calls` 表补 `step`/`thinking` 列（不删数据） |
| `models.py` | ORM 模型（8 张表） |
| `repos/__init__.py` | 聚合各表数据访问模块 |
| `repos/users.py` | 用户 |
| `repos/conversations.py` | 会话与状态读写 |
| `repos/messages.py` | 消息追加与按序读取 |
| `repos/attachments.py` | 附件元数据 |
| `repos/problems.py` | 题目模型 |
| `repos/evidence.py` | 证据记录 |
| `repos/llm_calls.py` | 模型调用日志 |
