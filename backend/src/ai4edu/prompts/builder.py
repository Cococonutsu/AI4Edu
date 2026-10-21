"""系统提示词的唯一组装出口（对齐 cc 的 `builder.py`）。

文字全部在 `sections.py` 的 Python 常量里（回合内短文字在
`config/prompts/reminders.yaml`）。`build_system_prompt` 按固定顺序拼装
具名段落：静态主体（身份、教学方式、意图路由、回复格式、画图与可视化、
联网查询、读题与拆题、诊断与判据）+ 动态的辅导状态摘要（每一步模型调用前重算）。
改动任何文字时提升对应版本号并同步更新
`tests/backend/prompts/golden/` 的金样例。

对应 `docs/architecture.md` 第 2.1 节（提示词唯一出口）。
"""

from __future__ import annotations

from ai4edu.prompts.sections import (
    get_diagnosis_section,
    get_figure_section,
    get_intro_section,
    get_problem_decomposition_section,
    get_intent_routing_section,
    get_reply_format_section,
    get_teaching_style_section,
    get_tutor_state_section,
    get_web_tools_section,
    render_template,
)
from ai4edu.tutoring.framework import (
    ConfigError,
    GradeBand,
    TutoringConfig,
)
from ai4edu.tutoring.problem import ProblemModel
from ai4edu.tutoring.state import TutorState

# 版本号随文字内容变化提升；文字搬进代码不改变内容，版本不变。
TUTOR_SYSTEM_VERSION = "tutor-2026.10.21-1"


def _grade_band_or_error(cfg: TutoringConfig, grade_band: str) -> GradeBand:
    band = cfg.grade_bands.get(grade_band)
    if band is None:
        raise ConfigError(
            f"grade_bands.yaml 中没有学段 {grade_band!r}；"
            f"可用：{'、'.join(cfg.grade_bands)}"
        )
    return band


def build_system_prompt(
    cfg: TutoringConfig,
    *,
    grade: int,
    grade_band: str,
    state: TutorState,
    problem: ProblemModel | None,
) -> str:
    """生成当前回合的辅导系统提示词。"""

    band = _grade_band_or_error(cfg, grade_band)
    sections = [
        get_intro_section(grade_band_name=band.name, grade=grade),
        get_teaching_style_section(band),
        get_intent_routing_section(),
        get_reply_format_section(),
        get_figure_section(),
        get_web_tools_section(),
        get_problem_decomposition_section(
            domain_ids="、".join(domain_ids(cfg, grade_band)),
            domain_templates=domain_templates_text(cfg, grade_band),
        ),
        get_diagnosis_section(
            cfg.framework, max_support_level=cfg.policy.max_support_level
        ),
        get_tutor_state_section(state, problem),
    ]
    return "\n\n".join(sections) + "\n"


# ---- 学段领域模板的选取与渲染（供"读题与拆题"段落使用） ----


def domain_ids(cfg: TutoringConfig, grade_band: str) -> list[str]:
    """返回适用于该学段的领域 id，顺序与 `domains.yaml` 一致。"""

    return [
        domain_id
        for domain_id, domain in cfg.domains.domains.items()
        if grade_band in domain.bands
    ]


def _stage_label(cfg: TutoringConfig, stage: str) -> str:
    """取阶段说明中冒号前的短标签，如 `理解题意`。"""

    text = cfg.domains.stages.get(stage, stage)
    return text.split("：", 1)[0].strip() or stage


def domain_templates_text(cfg: TutoringConfig, grade_band: str) -> str:
    """把适用于该学段的领域模板渲染成 Markdown，供"读题与拆题"段落使用。"""

    ids = domain_ids(cfg, grade_band)
    if not ids:
        return f"（{grade_band} 学段没有专用领域模板，请按 general 领域拆解。）"

    blocks: list[str] = []
    for domain_id in ids:
        domain = cfg.domains.domains[domain_id]
        lines = [f"#### {domain.name}（domain: `{domain_id}`）", "", "关注点："]
        for stage, focus in domain.focus.items():
            lines.append(f"- {_stage_label(cfg, stage)}（{stage}）：{focus}")
        gaps = (
            "；".join(domain.common_concept_gaps)
            if domain.common_concept_gaps
            else "（无）"
        )
        lines.append(f"- 常见概念缺口：{gaps}")
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


__all__ = [
    "TUTOR_SYSTEM_VERSION",
    "build_system_prompt",
    "domain_ids",
    "domain_templates_text",
]
