"""加载并校验诊断框架配置（`config/framework/*.yaml`）。

把规则集中成 `TutoringConfig`，供状态机、决策引擎和提示词组装
（`prompts/builder.py`）使用。本模块只做加载与校验，不包含任何教学
判定逻辑，也不读取提示词模板（那是 `prompts/loader.py` 的职责）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

# 领域模板只允许出现在这三个学段。
GRADE_BAND_NAMES: tuple[str, ...] = ("primary", "junior", "senior")


def grade_band_for(grade: int) -> str:
    """按年级返回学段名称：1–6 为小学（primary），7–9 为初中（junior），
    10–12 为高中（senior）。

    非整数或不在 1–12 范围内时抛出 `ValueError`。
    """
    if not isinstance(grade, int) or isinstance(grade, bool):
        raise ValueError("年级必须在 1–12 之间")
    if 1 <= grade <= 6:
        return "primary"
    if 7 <= grade <= 9:
        return "junior"
    if 10 <= grade <= 12:
        return "senior"
    raise ValueError("年级必须在 1–12 之间")


ModelT = TypeVar("ModelT", bound=BaseModel)


class ConfigError(Exception):
    """配置缺失、格式错误或前后矛盾。信息中应指出文件与键。"""


class SoloLevelDef(BaseModel):
    name: str
    criterion: str


class GapTypeDef(BaseModel):
    name: str
    action: str
    extension_only: bool = False


class ActionDef(BaseModel):
    name: str
    guidance: str


class FrameworkConfig(BaseModel):
    """`config/framework/framework.yaml`。"""

    version: str
    solo_levels: dict[str, SoloLevelDef]
    support_levels: dict[str, str]
    gap_types: dict[str, GapTypeDef]
    actions: dict[str, ActionDef]


class DomainDef(BaseModel):
    name: str
    bands: list[str]
    focus: dict[str, str]
    common_concept_gaps: list[str] = Field(default_factory=list)


class DomainsConfig(BaseModel):
    """`config/framework/domains.yaml`。"""

    stages: dict[str, str]
    domains: dict[str, DomainDef]


class GradeBand(BaseModel):
    """`config/framework/grade_bands.yaml` 中的一个学段。"""

    name: str
    grades: list[int]
    style: str
    max_question_sentences: int


class PolicyConfig(BaseModel):
    """`config/framework/policy.yaml`。"""

    stuck_turns_to_escalate: int
    help_request_escalates: bool
    max_support_level: str
    initial_support_level: str
    empty_step_retry_limit: int
    # 同一道题中"只报答案求对错"超过这个次数后婉拒逐个确认。
    answer_probe_limit: int = 2


class TutoringConfig(BaseModel):
    """四份框架 YAML 的聚合结果。"""

    framework: FrameworkConfig
    domains: DomainsConfig
    grade_bands: dict[str, GradeBand]
    policy: PolicyConfig


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:  # 文件不存在或无法读取
        raise ConfigError(f"无法读取配置文件 {path}：{exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path.name} 不是合法的 YAML：{exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name} 的顶层必须是映射（key: value）")
    return data


def _parse_model(model: type[ModelT], data: Any, filename: str) -> ModelT:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"{filename} 格式错误：{exc}") from exc


def _check_framework_consistency(framework: FrameworkConfig) -> None:
    for gap_name, gap in framework.gap_types.items():
        if gap.action not in framework.actions:
            raise ConfigError(
                f"framework.yaml 中 gap_types.{gap_name}.action 指向不存在的动作 "
                f"{gap.action!r}；actions 中只有：{'、'.join(framework.actions) or '（空）'}"
            )


def _check_domain_consistency(domains: DomainsConfig) -> None:
    for domain_name, domain in domains.domains.items():
        invalid = [band for band in domain.bands if band not in GRADE_BAND_NAMES]
        if invalid:
            raise ConfigError(
                f"domains.yaml 中 domains.{domain_name}.bands 含非法学段 "
                f"{invalid[0]!r}；只能是 {'、'.join(GRADE_BAND_NAMES)}"
            )


def _check_policy_consistency(policy: PolicyConfig, framework: FrameworkConfig) -> None:
    for key in ("max_support_level", "initial_support_level"):
        value = getattr(policy, key)
        if value not in framework.support_levels:
            raise ConfigError(
                f"policy.yaml 中 {key}={value!r} 不是 framework.yaml 定义的支持等级；"
                f"可用：{'、'.join(framework.support_levels)}"
            )
    if policy.stuck_turns_to_escalate < 1:
        raise ConfigError("policy.yaml 中 stuck_turns_to_escalate 必须 >= 1")


def load_config(config_dir: Path) -> TutoringConfig:
    """加载 `config_dir/framework/` 下的全部规则并做一致性校验。"""

    framework_dir = Path(config_dir) / "framework"

    framework = _parse_model(
        FrameworkConfig,
        _read_yaml(framework_dir / "framework.yaml"),
        "framework.yaml",
    )
    domains = _parse_model(
        DomainsConfig,
        _read_yaml(framework_dir / "domains.yaml"),
        "domains.yaml",
    )
    try:
        grade_bands = TypeAdapter(dict[str, GradeBand]).validate_python(
            _read_yaml(framework_dir / "grade_bands.yaml")
        )
    except ValidationError as exc:
        raise ConfigError(f"grade_bands.yaml 格式错误：{exc}") from exc
    policy = _parse_model(
        PolicyConfig,
        _read_yaml(framework_dir / "policy.yaml"),
        "policy.yaml",
    )

    _check_framework_consistency(framework)
    _check_domain_consistency(domains)
    _check_policy_consistency(policy, framework)

    return TutoringConfig(
        framework=framework,
        domains=domains,
        grade_bands=grade_bands,
        policy=policy,
    )


