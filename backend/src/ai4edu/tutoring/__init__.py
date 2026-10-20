"""辅导领域核心（纯逻辑）。

只依赖 pydantic、pyyaml 与标准库；不调用模型、不访问网络或数据库、
不产出提示词文字（提示词组装在 `prompts/`）。调用方传入 `config_dir`，
本包不读取全局设置。
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
    load_config,
)
from .policy import (
    PolicyError,
    decide,
    general_decision,
    start_problem,
)
from .problem import (
    Answer,
    ProblemModel,
    Relation,
    Subtask,
    relation_order,
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
    "decide",
    "general_decision",
    "load_config",
    "raise_support",
    "relation_order",
    "solo_rank",
    "start_problem",
    "support_rank",
    "validate_against",
]
