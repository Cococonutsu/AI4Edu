# config/

可调整的教学规则。代码只加载，不在代码里重复定义这些内容。由总调度维护。

| 路径 | 内容 | 读取方 |
|---|---|---|
| `framework/framework.yaml` | SOLO 层次、支持等级、缺口类型、动作及其引导说明；`version` | `tutoring/framework.py` |
| `framework/domains.yaml` | 知识领域与子任务拆解模板 | `prompts/builder.py` → 分析器提示词 |
| `framework/grade_bands.yaml` | 小学/初中/高中的表达风格 | `prompts/builder.py` |
| `framework/policy.yaml` | 规则引擎阈值 | `tutoring/policy.py` |

所有给模型的文字都不在本目录（系统提示词段落与回合内短文字都在
`backend/src/ai4edu/prompts/` 的 Python 常量里，对齐 cc 的做法）。占位符
格式 `{name}`，缺失取值时读取方报错而不是留空。修改 YAML 规则后提升
`framework.yaml` 的 `version`。
