# prompts/

**所有给模型看的文字的唯一出口**（`docs/architecture.md` 2.1），结构对齐
cc 的 builder/sections 模式：提示词文字是本包 Python 模块里的常量与段落
函数，builder 按固定顺序组装并携带版本号；回合内短文字在
`reminders.py` 的 Python 常量。工具的
`description` 与参数说明属于工具定义，留在工具文件里。

| 文件 | 内容 |
|---|---|
| `__init__.py` | 包导出 |
| `sections.py` | 全部提示词文字：辅导系统提示词的静态主体按小节切成具名段落（`get_intro_section`、`get_teaching_style_section`…），辅导中的诊断 `get_diagnosis_section`（填写要求 + 按 `framework.yaml` 渲染的 SOLO 层次、缺口类型与支持等级 + 收到决策后的约束；判据来自配置，引导文字为常量），"读题与拆题"段落 `get_problem_decomposition_section`（拆题规则 + 本学段领域模板），辅导状态摘要的段落模板与动态渲染 `get_tutor_state_section`（每步重算）；`render_template` 统一处理 `{{name}}` 占位符 |
| `builder.py` | 唯一组装出口：`build_system_prompt`（按固定顺序拼静态段、读题与拆题段、诊断判据段 + 状态摘要段）；版本常量 `TUTOR_SYSTEM_VERSION` 等（改文字必须提版本）；学段领域模板选取 |
| `reminders.py` | 回合内短文字（守卫提醒、工具结果指令、学生可见错误）的 Python 常量、`REMINDERS_VERSION` 与 `Reminders` 视图（`{name}` 占位填充，缺参报错） |

改动 `sections.py` 里的任何文字时：提升 `builder.py` 对应版本号、同步更新
`tests/backend/prompts/golden/` 金样例（`tests/backend/prompts/test_builder.py`
会逐字比对）。
