"""所有给模型看的文字的唯一出口（`docs/architecture.md` 2.1）。

结构对齐 cc 的 builder/sections 模式：系统提示词文字集中在 `sections.py` 的
Python 常量与段落函数里，`builder.py` 按固定顺序组装并携带版本号；回合内
短文字（提醒、工具结果指令、学生可见错误）在 `reminders.py` 的 Python
常量里。工具的 `description` 与参数说明属于工具定义，留在工具文件里。
"""

from ai4edu.prompts.builder import (
    TUTOR_SYSTEM_VERSION,
    build_system_prompt,
    domain_ids,
    domain_templates_text,
)
from ai4edu.prompts.reminders import REMINDERS_VERSION, Reminders
from ai4edu.prompts.sections import render_template

__all__ = [
    "REMINDERS_VERSION",
    "Reminders",
    "TUTOR_SYSTEM_VERSION",
    "build_system_prompt",
    "domain_ids",
    "domain_templates_text",
    "render_template",
]
