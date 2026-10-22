# tutoring/

辅导领域核心，**纯逻辑**：不调用模型、不访问网络、不直接访问数据库、
不产出提示词文字（提示词组装在 `prompts/builder.py`）。全部可单元测试。

| 文件 | 内容 |
|---|---|
| `__init__.py` | 包导出：配置、题目模型、诊断、状态、决策 |
| `framework.py` | 加载并校验 `config/framework/*.yaml`（框架、领域、学段、策略），不读提示词模板（那是 `prompts/loader.py` 的职责） |
| `problem.py` | 题目模型 `ProblemModel`（Pydantic），格式见 `docs/tutoring-framework.md` 第 3 节 |
| `diagnosis.py` | 诊断输入 `Diagnosis`（Pydantic）与 `validate_against`，格式见同文第 4 节 |
| `state.py` | `TutorState`、`SubtaskState`、`Phase`、`SoloLevel`、`SupportLevel` 及等级比较工具 |
| `decision.py` | `Decision`：动作、目标、支持上限与 `must_not_reveal`（避免与 `state.py` 循环导入） |
| `policy.py` | `decide(state, problem, diagnosis, cfg) -> (new_state, Decision)`，实现 `docs/architecture.md` 4.4 |
