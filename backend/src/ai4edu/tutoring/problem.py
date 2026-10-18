"""题目模型 `ProblemModel`：`analyze_problem` 输出、规则引擎与提示词的共同输入。

字段与校验规则见 `docs/tutoring-framework.md` 第 3 节。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

Stage = Literal["understand", "represent", "relate", "solve", "verify", "extend"]
RelationKind = Literal[
    "element", "relation", "justification", "verification", "generalization"
]
GradeBandName = Literal["primary", "junior", "senior"]

STAGES: tuple[str, ...] = (
    "understand",
    "represent",
    "relate",
    "solve",
    "verify",
    "extend",
)


def _duplicates(items: list[str]) -> list[str]:
    seen: set[str] = set()
    repeated: list[str] = []
    for item in items:
        if item in seen and item not in repeated:
            repeated.append(item)
        seen.add(item)
    return repeated


class Relation(BaseModel):
    """解题所需的一条要素、关系、依据、检验或概括。顺序即前提顺序。"""

    id: str
    kind: RelationKind
    text: str
    depends_on: list[str] = Field(default_factory=list)


class Subtask(BaseModel):
    """一个辅导子任务。`extend` 阶段只能作为可选拓展。"""

    id: str
    stage: Stage
    title: str
    goal: str
    required_relations: list[str] = Field(default_factory=list)
    completion_criteria: str
    optional: bool = False


class Check(BaseModel):
    """可用 SymPy 验算的校验式。

    - `solve`：解 `equation = 0`，`symbol` 为未知量，`expect` 为期望值；
    - `equal`：判断 `left` 与 `right` 是否相等。
    """

    kind: Literal["solve", "equal"]
    equation: str | None = None
    symbol: str | None = None
    expect: str | None = None
    left: str | None = None
    right: str | None = None

    @model_validator(mode="after")
    def _check_required_fields(self) -> "Check":
        if self.kind == "solve":
            missing = [
                name for name in ("equation", "symbol", "expect") if not getattr(self, name)
            ]
            if missing:
                raise ValueError(
                    f"solve 类型的 check 缺少字段：{'、'.join(missing)}"
                )
        else:
            missing = [name for name in ("left", "right") if not getattr(self, name)]
            if missing:
                raise ValueError(f"equal 类型的 check 缺少字段：{'、'.join(missing)}")
        return self


class Answer(BaseModel):
    text: str
    latex: str | None = None


class ProblemModel(BaseModel):
    """题目模型。关系按前提顺序排列，子任务按推进顺序排列。"""

    statement: str
    grade_band: GradeBandName
    domain: str
    givens: list[str] = Field(default_factory=list)
    goal: str
    answer: Answer
    relations: list[Relation] = Field(default_factory=list)
    subtasks: list[Subtask] = Field(default_factory=list)
    checks: list[Check] = Field(default_factory=list)
    reference_solution: str = ""

    @model_validator(mode="after")
    def _validate_structure(self) -> "ProblemModel":
        relation_ids = [relation.id for relation in self.relations]
        repeated_relations = _duplicates(relation_ids)
        if repeated_relations:
            raise ValueError(f"关系 id 重复：{'、'.join(repeated_relations)}")

        subtask_ids = [subtask.id for subtask in self.subtasks]
        repeated_subtasks = _duplicates(subtask_ids)
        if repeated_subtasks:
            raise ValueError(f"子任务 id 重复：{'、'.join(repeated_subtasks)}")

        relation_index = {rid: index for index, rid in enumerate(relation_ids)}
        for relation in self.relations:
            for dependency in relation.depends_on:
                if dependency not in relation_index:
                    raise ValueError(
                        f"关系 {relation.id} 的 depends_on 引用了不存在的关系 {dependency}"
                    )
                if relation_index[dependency] >= relation_index[relation.id]:
                    raise ValueError(
                        f"关系 {relation.id} 的 depends_on 只能引用排在前面的关系，"
                        f"{dependency} 不满足"
                    )

        for subtask in self.subtasks:
            for relation_id in subtask.required_relations:
                if relation_id not in relation_index:
                    raise ValueError(
                        f"子任务 {subtask.id} 的 required_relations 引用了"
                        f"不存在的关系 {relation_id}"
                    )
            if subtask.stage == "extend" and not subtask.optional:
                raise ValueError(
                    f"子任务 {subtask.id} 处于 extend 阶段，必须 optional=True"
                )
            if not subtask.optional and not subtask.required_relations:
                raise ValueError(
                    f"必做子任务 {subtask.id} 至少要关联一个关系；"
                    f"否则规则引擎会把它当作已满足完成标准"
                )

        required_count = sum(1 for subtask in self.subtasks if not subtask.optional)
        if not 1 <= required_count <= 5:
            raise ValueError(
                f"必做子任务数量应为 1–5 个，当前 {required_count} 个"
            )
        return self


def relation_order(problem: ProblemModel) -> dict[str, int]:
    """关系 id → 在题目模型中的序号，用于“最靠前的缺口”判定。"""

    return {relation.id: index for index, relation in enumerate(problem.relations)}
