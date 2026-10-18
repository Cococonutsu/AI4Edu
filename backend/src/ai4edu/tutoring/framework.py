"""加载并校验诊断框架配置与提示词模板。

读取 `config/framework/*.yaml` 与 `config/prompts/*.md`，把规则集中成
`TutoringConfig`，供状态机、决策引擎和提示词组装使用。本模块只做加载与校验，
不包含任何教学判定逻辑。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

# 领域模板只允许出现在这三个学段。
GRADE_BAND_NAMES: tuple[str, ...] = ("primary", "junior", "senior")

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_PROMPT_VERSION_RE = re.compile(r"prompt_version\s*:\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_LEADING_COMMENT_RE = re.compile(r"\s*<!--.*?-->[ \t]*\r?\n?", re.DOTALL)

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
    diagnosis_retry_limit: int
    # 同一道题中"只报答案求对错"超过这个次数后婉拒逐个确认。
    answer_probe_limit: int = 2


class TutoringConfig(BaseModel):
    """四份 YAML 与三份提示词模板的聚合结果。"""

    framework: FrameworkConfig
    domains: DomainsConfig
    grade_bands: dict[str, GradeBand]
    policy: PolicyConfig
    tutor_system: str
    tutor_system_version: str
    analyzer: str
    analyzer_version: str
    solver_check: str
    solver_check_version: str

    @property
    def prompt_versions(self) -> dict[str, str]:
        """三个提示词模板各自的版本号，便于写入模型调用日志。"""

        return {
            "tutor_system": self.tutor_system_version,
            "analyzer": self.analyzer_version,
            "solver_check": self.solver_check_version,
        }


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


def _read_prompt(path: Path) -> tuple[str, str]:
    """读取提示词原文，并从首行注释中解析 `prompt_version`。"""

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"无法读取提示词模板 {path}：{exc}") from exc
    if not text.strip():
        raise ConfigError(f"提示词模板 {path.name} 为空")

    first_line = text.splitlines()[0] if text.splitlines() else ""
    match = _PROMPT_VERSION_RE.search(first_line)
    if match is None:
        raise ConfigError(
            f"{path.name} 首行注释缺少 prompt_version，应形如 "
            f"`<!-- prompt_version: xxx -->`"
        )
    return text, match.group(1)


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
    """加载 `config_dir` 下的全部规则与提示词，并做一致性校验。"""

    config_dir = Path(config_dir)
    framework_dir = config_dir / "framework"
    prompts_dir = config_dir / "prompts"

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

    tutor_system, tutor_system_version = _read_prompt(prompts_dir / "tutor_system.md")
    analyzer, analyzer_version = _read_prompt(prompts_dir / "analyzer.md")
    solver_check, solver_check_version = _read_prompt(prompts_dir / "solver_check.md")

    return TutoringConfig(
        framework=framework,
        domains=domains,
        grade_bands=grade_bands,
        policy=policy,
        tutor_system=tutor_system,
        tutor_system_version=tutor_system_version,
        analyzer=analyzer,
        analyzer_version=analyzer_version,
        solver_check=solver_check,
        solver_check_version=solver_check_version,
    )


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
    """把适用于该学段的领域模板渲染成 Markdown，供分析器提示词使用。"""

    ids = domain_ids(cfg, grade_band)
    if not ids:
        return f"（{grade_band} 学段没有专用领域模板，请按 general 领域拆解。）"

    blocks: list[str] = []
    for domain_id in ids:
        domain = cfg.domains.domains[domain_id]
        lines = [f"### {domain.name}（domain: `{domain_id}`）", "", "关注点："]
        for stage, focus in domain.focus.items():
            lines.append(f"- {_stage_label(cfg, stage)}（{stage}）：{focus}")
        gaps = "；".join(domain.common_concept_gaps) if domain.common_concept_gaps else "（无）"
        lines.append(f"- 常见概念缺口：{gaps}")
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


def render_template(template: str, values: dict[str, str]) -> str:
    """替换 `{{name}}` 占位符，并去掉首行的 `<!-- ... -->` 注释。

    模板中出现但 `values` 未提供的占位符会抛 `ConfigError`，而不是留空。
    """

    body = _LEADING_COMMENT_RE.sub("", template, count=1)
    missing: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            missing.append(key)
            return match.group(0)
        return str(values[key])

    rendered = _PLACEHOLDER_RE.sub(_replace, body)
    if missing:
        unique = list(dict.fromkeys(missing))
        placeholders = "、".join(f"{{{{{key}}}}}" for key in unique)
        raise ConfigError(f"提示词模板缺少占位符取值：{placeholders}")
    return rendered
