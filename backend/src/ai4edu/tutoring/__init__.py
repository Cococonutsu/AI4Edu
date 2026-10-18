"""辅导领域核心（纯逻辑）。

只依赖 pydantic、pyyaml 与标准库；不调用模型、不访问网络或数据库。
调用方传入 `config_dir`，本包不读取全局设置。
"""

from __future__ import annotations

from .decision import Decision
from .diagnosis import Diagnosis, DiagnosisError, Gap, validate_against
from .framework import (
    ActionDef,
    ConfigError,
    DomainDef,
    DomainsConfig,
    FrameworkConfig,
    GapTypeDef,
    GradeBand,
    PolicyConfig,
    SoloLevelDef,
    TutoringConfig,
    domain_ids,
    domain_templates_text,
    load_config,
    render_template,
)
from .policy import (
    PolicyError,
    decide,
    general_decision,
    start_problem,
)
from .problem import (
    Answer,
    Check,
    ProblemModel,
    Relation,
    Subtask,
    relation_order,
)
from .prompt_builder import (
    build_analyzer_prompt,
    build_solver_check_prompt,
    build_tutor_system_prompt,
)
from .state import (
    MathStatus,
    Phase,
    SoloLevel,
    SubtaskState,
    SubtaskStatus,
    SupportLevel,
    TutorState,
    raise_support,
    solo_rank,
    support_rank,
)

__all__ = [
    "ActionDef",
    "Answer",
    "Check",
    "ConfigError",
    "Decision",
    "Diagnosis",
    "DiagnosisError",
    "DomainDef",
    "DomainsConfig",
    "FrameworkConfig",
    "Gap",
    "GapTypeDef",
    "GradeBand",
    "MathStatus",
    "Phase",
    "PolicyConfig",
    "PolicyError",
    "ProblemModel",
    "Relation",
    "SoloLevel",
    "SoloLevelDef",
    "Subtask",
    "SubtaskState",
    "SubtaskStatus",
    "SupportLevel",
    "TutorState",
    "TutoringConfig",
    "build_analyzer_prompt",
    "build_solver_check_prompt",
    "build_tutor_system_prompt",
    "decide",
    "domain_ids",
    "domain_templates_text",
    "general_decision",
    "load_config",
    "raise_support",
    "relation_order",
    "render_template",
    "solo_rank",
    "start_problem",
    "support_rank",
    "validate_against",
]
