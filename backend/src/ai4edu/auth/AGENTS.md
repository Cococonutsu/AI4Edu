# auth/

账号鉴权。不开放注册，账号由 `cli/` 创建。

| 文件 | 内容 |
|---|---|
| `__init__.py` | 导出密码、会话与当前用户 |
| `passwords.py` | argon2 哈希与校验 |
| `sessions.py` | 生成随机 token、存哈希、校验与过期、删除 |
| `deps.py` | FastAPI 依赖 `current_user`：从 cookie `ai4edu_session` 取用户，失败返回 401 |
