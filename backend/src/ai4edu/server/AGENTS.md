# server/

HTTP 层（FastAPI）。只做：解析请求、鉴权、调用下层、序列化响应、NDJSON 流。不写业务规则。

边界：
- 学生可见消息由 `serializers.py` 统一转换，过滤思考文本、工具参数与结果（见 `docs/architecture.md` 第 6 节）。
- 所有路由通过 `auth.deps.current_user` 取得用户，并按 `user_id` 查询。
- 生成任务登记在 `streaming.py` 的运行表中，`/stop` 通过它取消。

| 文件 | 内容 |
|---|---|
| `__init__.py` | 包标记 |
| `app.py` | `create_app()`、`app`；挂载路由、启动时建表 |
| `routes/__init__.py` | 路由包标记 |
| `routes/auth.py` | `/api/auth/*` |
| `routes/conversations.py` | 会话增删改查 |
| `routes/messages.py` | 发送消息（后台任务 + `asyncio.Queue` → NDJSON 流）、停止生成；同一会话同时只允许一个任务 |
| `routes/attachments.py` | 图片上传与下载 |
| `schemas.py` | 请求/响应 Pydantic 模型 |
| `serializers.py` | 内部消息 → 学生可见消息 |
| `streaming.py` | 智能体事件 → NDJSON 行；运行中任务登记与取消 |
