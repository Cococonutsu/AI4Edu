# tests/backend/

后端测试，子目录对应 `backend/src/ai4edu/` 的子包。运行：`cd backend && uv run pytest ../tests/backend`。

| 路径 | 覆盖 |
|---|---|
| `conftest.py` | 隔离 `DATA_DIR`；`db_engine` / `session_factory` / `db_session` 临时数据库 fixture；`seed` 学生与会话 |
| `fakes.py` | `FakeLLMClient`：按脚本返回流式（思考/正文/分片工具调用/usage）与非流式响应并记录每次请求（配合 `GLMProvider` 断言厂商格式）；`FakeProvider`：按脚本产出模型事件/响应并记录 `ModelRequest`（断言循环与引擎行为）；异常脚本项直接抛出 |
| `test_layering.py` | AST 检查依赖方向：`core/query_loop` 只依赖参数、只有 `api/glm|client` 导入 `openai`、`models/` 不导入兄弟包、只有 `prompts/` 读模板文件、`storage/repos` 的调用方白名单 |
| `api/test_usage_parsing.py` | usage 解析：OpenAI/DeepSeek/裸三种缓存命中字段形态与缺省为 0 |
| `models/test_content.py` | 工具结果富内容：`tool_result_text` 渲染、块列表 JSON 往返、旧字符串数据兼容 |
| `utils/test_errors.py` | 全部应用异常继承 `AI4EduError` 且不误捕系统异常 |
| `models/test_message_sequence.py` | 消息序列规范化与校验：合并（纯文字空行连接/带图拼接）、补/删/重排工具结果、开头清理、未知 role 拒绝、随机历史性质测试 |
| `api/test_glm.py` | wire 格式（system 在首、图片在文字前、tool_calls、tool 消息、思考只回传本回合、空 system 省略）、`thinking=off` 的 `extra_body`、tools/tool_choice 映射、流式分片拼接、非法工具参数、JSON 围栏解析、openai 异常 → `ProviderError.recoverable` |
| `api/test_client.py` | `make_provider` 默认 glm；未知厂商报错 |
| `core/test_query_engine.py` | 回合守卫：读题后不重复诊断、已发送正文提醒、点问题直接写正文、插问正文不被丢弃、空步重试、每次请求序列合法（含残缺历史）、空回合错误事件、诊断后关思考且 `llm_calls` 记录 step/thinking |
| `core/test_query_loop.py` | 可恢复 `ProviderError` 重试（退避 1s/2s）并成功、不可恢复立即失败、重试耗尽、正文已下发不重试、max_steps、输出截断的额度升级重试/正文续写/恢复上限 |
| `hooks/test_step_mode.py` | `choose_step_mode`：第 1 步开思考、诊断/分析后关思考、工具报错保持开思考、tool_choice 恒 auto |
| `prompts/test_builder.py` | 提示词组装与冻结基线逐字一致（`golden/` 金样例）；reminders 占位符缺失报错 |
| `prompts/golden/` | 冻结的提示词输出基线；改 `prompts/sections.py` 文字时必须同步更新并提版本 |
| `tools/test_figure.py` | 图形描述校验：未知名称、不存在的点引用、算式字符白名单；下发数据与给模型的文字分开 |
| `tools/test_analyze_problem.py` | 学段来自账号、参数 schema 不含学段、不调用模型并进入辅导、题目模型不合格时返回具体原因 |
| `tools/test_base.py` | 模型调用日志并发写串行 |
| `server/test_app.py` | 启动时缺少 LLM_API_KEY 的日志 |
| `server/test_isolation.py` | 跨学生隔离：会话详情/改名/删除/发消息/停止/下载附件/挂附件到他人会话一律 404，会话列表互不可见 |
| `server/test_auth.py` | `PATCH /auth/me`：改名/改年级与学段推导、只改一项、空名/超长/年级越界或非整数 422 且资料未变、未知字段拒绝、未登录 401、改后重新登录可见 |
| `server/test_messages.py` | 流式回答期间请求数据库会话已关闭，不阻塞其他请求 |
| `server/test_background_runs.py` | 浏览器断开不取消生成、任务结束自动移出登记表、`/stop` 仍可取消、每个学生同时生成的会话数上限（429） |
| `test_config.py` | 不依赖 AGENTS.md 定位仓库根目录 |
| `tutoring/test_policy.py` | 规则引擎：完成推进、错误优先、SU 取证、缺口排序、支持升级与不回落、独立证据、must_not_reveal、证据原文校验、answer probe（询问依据/婉拒/不升级/不误判完成） |
| `storage/test_db_concurrency.py` | SQLite WAL：未结束的读事务不阻塞其他连接写入（防 database is locked） |
| `storage/test_migration.py` | 旧 `llm_calls` 表 `init_db` 补列（step/thinking）不删数据；迁移幂等 |

待补（扩展到这些模块时先补测试）：`hooks/guard` 守卫的独立用例、`server/serializers` 可见消息过滤、用户隔离。
