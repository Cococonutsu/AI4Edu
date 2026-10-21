"""`draw_figure`：老师给出结构化图形描述，学生在右侧面板看到可拖动的图示。

形状用一份**受校验的结构化描述**表达（点、线段、多边形、曲线、观察值、
参数与移动轨迹），不执行模型给出的任意脚本：

- 后端在这里做校验（字段、数量、算式字符与名字白名单），不合格就返回
  具体原因让老师修正；
- 前端用 JSXGraph 与一个只认白名单运算的求值器渲染（`frontend/src/utils/figure.ts`），
  拖动参数或播放轨迹时重新计算坐标与观察值。

说明文字（`caption`、轨迹的 `note`）是给学生看的，在这里写入；给模型看的
工具结果文字仍来自 `prompts/reminders`。

对应 `docs/architecture.md` 第 5 节（工具）。
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from ai4edu.tools.base import BaseTool, ToolContext, ToolResult

# ---- 算式白名单 ----

_ALLOWED_EXPR_CHARS = re.compile(r"^[0-9A-Za-z_.+\-*/^(),\s]+$")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?")
_FUNCTIONS = {"sqrt", "abs", "sin", "cos", "tan", "min", "max"}
_CONSTANTS = {"pi"}
_MAX_EXPRESSION_LENGTH = 120

PointId = str
_PARAM_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,7}$")
_POINT_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,2}$")
_DISPLAY_NAME_RE = re.compile(r"^[^\n\r<>]{1,12}$")
# given 是条件清单，出现这些标记说明写进了推导结论。
_DERIVATION_RE = re.compile(r"⇒|⇔|所以|因此|故|即")


class FigureError(ValueError):
    """图形描述不合格；消息直接给模型看。"""


class Parameter(BaseModel):
    """可拖动参数。没给 min/max 时默认取初始值上下 5（初值非负时下限为 0）。"""

    name: str
    label: str = ""
    value: float
    min: float | None = None
    max: float | None = None
    step: float = 0.1

    @model_validator(mode="after")
    def _check(self) -> "Parameter":
        if not _PARAM_NAME_RE.match(self.name):
            raise ValueError(f"参数名 {self.name!r} 只能用 1–8 个字母或数字，并以字母开头")
        if self.min is None:
            self.min = max(0.0, self.value - 5) if self.value >= 0 else self.value - 5
        if self.max is None:
            self.max = max(self.value + 5, self.min + 1)
        if not self.min < self.max:
            raise ValueError(f"参数 {self.name} 的 min 必须小于 max")
        if not self.min <= self.value <= self.max:
            raise ValueError(
                f"参数 {self.name} 的初始值 {self.value} 不在范围 "
                f"[{self.min}, {self.max}] 内；请调整 value 或 min/max"
            )
        if self.step <= 0:
            raise ValueError(f"参数 {self.name} 的 step 必须大于 0")
        return self


class PointSpec(BaseModel):
    id: PointId
    x: str
    y: str
    label: str = ""
    role: Literal["plain", "highlight"] = "plain"


class SegmentSpec(BaseModel):
    from_: str = Field(alias="from")
    to: str
    dashed: bool = False

    model_config = {"populate_by_name": True}


class PolygonSpec(BaseModel):
    points: list[str]
    label: str = ""


class CurveSpec(BaseModel):
    expression: str
    from_: float = Field(alias="from", default=0.1)
    to: float = 9.0
    label: str = ""

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _check(self) -> "CurveSpec":
        if not self.from_ < self.to:
            raise ValueError("曲线的 from 必须小于 to")
        return self


class CircleSpec(BaseModel):
    """圆：圆心 + 圆上一点，或圆心 + 半径算式（二选一）。"""

    center: str
    through: str | None = None
    radius: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "CircleSpec":
        if (self.through is None) == (self.radius is None):
            raise ValueError(
                "圆要给出 through（圆上一点）或 radius（半径算式），只给一个"
            )
        return self


class ReadoutSpec(BaseModel):
    label: str
    expression: str
    format: Literal["number", "fraction"] = "number"
    emphasis: bool = False


class TrajectoryStep(BaseModel):
    parameter: str
    from_: float = Field(alias="from")
    to: float
    seconds: float = 6.0
    note: str = ""

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _check(self) -> "TrajectoryStep":
        if self.seconds < 1 or self.seconds > 20:
            raise ValueError("移动时长应在 1–20 秒之间")
        return self


class FigureSpec(BaseModel):
    """一次可视化的完整描述（学生可见）。"""

    title: str
    caption: str = ""
    # 这张图依据的已知条件：题设里已经确定的内容。
    # 必须非空——没有确定的已知条件时，本来就不该画图。
    given: list[str] = Field(default_factory=list)
    # 代表"题目还没求出来的量"的参数名（如 D、E、k）。前端在滑块上标"待定"，
    # 让学生知道图里这部分是假设出来的，不是题目给定的。
    unknowns: list[str] = Field(default_factory=list)
    parameters: list[Parameter] = Field(default_factory=list)
    points: list[PointSpec] = Field(default_factory=list)
    segments: list[SegmentSpec] = Field(default_factory=list)
    polygons: list[PolygonSpec] = Field(default_factory=list)
    curves: list[CurveSpec] = Field(default_factory=list)
    circles: list[CircleSpec] = Field(default_factory=list)
    readouts: list[ReadoutSpec] = Field(default_factory=list)
    trajectory: list[TrajectoryStep] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> "FigureSpec":
        if not self.title.strip():
            raise ValueError("title 不能为空")
        if not self.given:
            raise ValueError(
                "given 不能为空：先列出这张图依据的已知条件（如“圆心在 y 轴上”“直线 x+2y-4=0”）。"
                "如果题目此刻还没有确定的图形可画，就不要调用 draw_figure，先用文字引导。"
            )
        if len(self.given) > 8:
            raise ValueError("given 最多 8 条")
        for item in self.given:
            if not item.strip() or len(item) > 60:
                raise ValueError("given 的每一条都要非空且不超过 60 字")
            if _DERIVATION_RE.search(item):
                raise ValueError(
                    f"given 只能列已知条件，不能写推导结论：{item!r}。"
                    "把推出的结果去掉，只写题设给出的内容。"
                )
        if len(self.title) > 60:
            raise ValueError("title 不能超过 60 字")
        if len(self.caption) > 160:
            raise ValueError("caption 不能超过 160 字")
        if len(self.parameters) > 6:
            raise ValueError("参数最多 6 个")
        if len(self.points) > 20:
            raise ValueError("点最多 20 个")
        if len(self.segments) > 30:
            raise ValueError("线段最多 30 条")
        if len(self.polygons) > 10:
            raise ValueError("多边形最多 10 个")
        if len(self.curves) > 4:
            raise ValueError("曲线最多 4 条")
        if len(self.circles) > 4:
            raise ValueError("圆最多 4 个")
        if len(self.readouts) > 8:
            raise ValueError("观察值最多 8 项")
        if len(self.trajectory) > 3:
            raise ValueError("移动轨迹最多 3 段")
        if not self.points and not self.curves:
            raise ValueError("至少要有 points 或 curves，否则图是空的")

        param_names = {param.name for param in self.parameters}
        if len(param_names) != len(self.parameters):
            raise ValueError("参数名不能重复")

        point_ids: set[str] = set()
        for point in self.points:
            if not _POINT_ID_RE.match(point.id):
                raise ValueError(f"点 id {point.id!r} 只能用 1–3 个字母或数字，并以字母开头")
            if point.id in point_ids:
                raise ValueError(f"点 id {point.id} 重复")
            point_ids.add(point.id)
            if point.label and not _DISPLAY_NAME_RE.match(point.label):
                raise ValueError(f"点 {point.id} 的 label 不能超过 12 个字符，也不能含换行")

        names = param_names | _CONSTANTS

        def check(expr: str, where: str, *, extra: set[str] | None = None) -> None:
            if not expr.strip():
                raise ValueError(f"{where} 的算式不能为空")
            if len(expr) > _MAX_EXPRESSION_LENGTH:
                raise ValueError(f"{where} 的算式不能超过 {_MAX_EXPRESSION_LENGTH} 个字符")
            if not _ALLOWED_EXPR_CHARS.match(expr):
                raise ValueError(f"{where} 的算式含有不允许的字符：{expr}")
            for token in _IDENT_RE.findall(expr):
                head = token.split(".", 1)[0]
                if "." in token:
                    if head not in point_ids or token.split(".", 1)[1] not in ("x", "y"):
                        raise ValueError(f"{where} 引用了不存在的点坐标 {token}（应写成 C.x 或 C.y）")
                elif token in _FUNCTIONS or token in names or (extra and token in extra):
                    continue
                else:
                    raise ValueError(
                        f"{where} 里出现了未定义的名称 {token}；只能使用参数名、"
                        f"{'点坐标（如 C.x）、' if point_ids else ''}pi 和函数 "
                        f"{'、'.join(sorted(_FUNCTIONS))}"
                    )

        for point in self.points:
            check(point.x, f"点 {point.id} 的 x")
            check(point.y, f"点 {point.id} 的 y")

        for segment in self.segments:
            for name in (segment.from_, segment.to):
                if name not in point_ids:
                    raise ValueError(f"线段引用了不存在的点 {name}")
        for polygon in self.polygons:
            if len(polygon.points) < 3:
                raise ValueError("多边形至少需要 3 个点")
            for name in polygon.points:
                if name not in point_ids:
                    raise ValueError(f"多边形引用了不存在的点 {name}")
        for circle in self.circles:
            if circle.center not in point_ids:
                raise ValueError(f"圆引用了不存在的点 {circle.center}")
            if circle.through is not None and circle.through not in point_ids:
                raise ValueError(f"圆引用了不存在的点 {circle.through}")
            if circle.radius is not None:
                check(circle.radius, "圆的半径")
        for curve in self.curves:
            check(curve.expression, "曲线", extra={"x"})
        for readout in self.readouts:
            if not readout.label.strip():
                raise ValueError("观察值的 label 不能为空")
            check(readout.expression, f"观察值「{readout.label}」的算式")
        for step in self.trajectory:
            if step.parameter not in param_names:
                raise ValueError(f"移动轨迹引用了不存在的参数 {step.parameter}")
        for name in self.unknowns:
            if name not in param_names:
                raise ValueError(
                    f"unknowns 里的 {name} 不是参数；待定量要做成可拖动的参数"
                )
        return self


def _validation_message(exc: ValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors()[:6]:
        location = ".".join(str(item) for item in error.get("loc", ()))
        message = str(error.get("msg"))
        parts.append(f"{location}: {message}" if location else message)
    return "；".join(parts) or str(exc)


def figure_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "面板标题，一句话说清这张图看什么，如“拖动 A 点，看面积怎么变”。",
            },
            "caption": {
                "type": "string",
                "description": "图上方的提示：学生看图时该注意哪两个量的关系。不超过 100 字。",
            },
            "given": {
                "type": "array",
                "description": (
                    "这张图依据的已知条件，逐条写出（如“直线 x+2y=4”“圆心在 y 轴上”）。"
                    "必须非空：题目还没有确定的图形可画时，不要调用本工具，先用文字引导。"
                ),
                "items": {"type": "string"},
            },
            "unknowns": {
                "type": "array",
                "description": (
                    "哪些参数代表题目还没求出来的量（如圆方程里的 D、E，反比例函数的 k）。"
                    "学生会看到它们标着“待定”。题目已确定的量不要放进来。"
                ),
                "items": {"type": "string"},
            },
            "parameters": {
                "type": "array",
                "description": "可拖动的参数（学生拖动滑块时整张图重新计算）。没有可变的量就不要传。",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "参数名，如 a、k，1–8 个字母或数字。"},
                        "label": {"type": "string", "description": "显示名，如“a（C 的横坐标）”。"},
                        "value": {"type": "number", "description": "初始值。"},
                        "min": {"type": "number", "description": "拖动下限；不给时取初值减 5（初值非负则不小于 0）。"},
                        "max": {"type": "number", "description": "拖动上限；不给时取初值加 5。"},
                        "step": {"type": "number", "description": "拖动步长，默认 0.1。"},
                    },
                    "required": ["name", "value"],
                },
            },
            "points": {
                "type": "array",
                "description": "图中的点。坐标写算式（可以用参数、pi、sqrt 等）。",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "点 id，如 A、C，1–3 个字母或数字。"},
                        "x": {"type": "string", "description": "横坐标算式，如 \"a\" 或 \"2*a\"。"},
                        "y": {"type": "string", "description": "纵坐标算式，如 \"k/a\"。"},
                        "label": {"type": "string", "description": "显示名，默认用 id。"},
                        "role": {
                            "type": "string",
                            "enum": ["plain", "highlight"],
                            "description": "highlight 用于题目中要重点观察的点（标成红点）。",
                        },
                    },
                    "required": ["id", "x", "y"],
                },
            },
            "segments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "from": {"type": "string", "description": "起点 id。"},
                        "to": {"type": "string", "description": "终点 id。"},
                        "dashed": {"type": "boolean", "description": "虚线用于辅助线。"},
                    },
                    "required": ["from", "to"],
                },
            },
            "polygons": {
                "type": "array",
                "description": "填充的多边形，如需要强调的面积。",
                "items": {
                    "type": "object",
                    "properties": {
                        "points": {"type": "array", "items": {"type": "string"}},
                        "label": {"type": "string"},
                    },
                    "required": ["points"],
                },
            },
            "curves": {
                "type": "array",
                "description": "函数图象，如反比例函数 y=k/x。表达式里用 x 作自变量，可带参数。",
                "items": {
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string", "description": "如 \"k/x\"。"},
                        "from": {"type": "number", "description": "左端点，默认 0.1。"},
                        "to": {"type": "number", "description": "右端点，默认 9。"},
                        "label": {"type": "string"},
                    },
                    "required": ["expression"],
                },
            },
            "circles": {
                "type": "array",
                "description": "圆。题目里的圆必须用这里画出来，不能只画圆心和一条线暗示它。",
                "items": {
                    "type": "object",
                    "properties": {
                        "center": {"type": "string", "description": "圆心点 id。"},
                        "through": {"type": "string", "description": "圆上一点 id（与 radius 二选一）。"},
                        "radius": {
                            "type": "string",
                            "description": "半径算式，如 \"sqrt(m^2+12)\".（与 through 二选一）",
                        },
                    },
                    "required": ["center"],
                },
            },
            "readouts": {
                "type": "array",
                "description": "右侧的观察值：随参数变化自动更新，学生就是看它们的值。",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "description": "显示名，如“S△BDE”或“S△BDE ÷ k”。"},
                        "expression": {
                            "type": "string",
                            "description": "算式。可用参数名、点坐标（如 C.x、C.y）、数字与 + - * / ^。",
                        },
                        "format": {
                            "type": "string",
                            "enum": ["number", "fraction"],
                            "description": "fraction 用于想显示成 1/4 这类分数的量。",
                        },
                        "emphasis": {
                            "type": "boolean",
                            "description": "突出显示（用于要让学生发现的不变量）。",
                        },
                    },
                    "required": ["label", "expression"],
                },
            },
            "trajectory": {
                "type": "array",
                "description": "打开面板时自动播放的移动轨迹：让某个参数从 from 变到 to。",
                "items": {
                    "type": "object",
                    "properties": {
                        "parameter": {"type": "string", "description": "参数名。"},
                        "from": {"type": "number"},
                        "to": {"type": "number"},
                        "seconds": {"type": "number", "description": "用时，1–20 秒，默认 6。"},
                        "note": {"type": "string", "description": "这段时间里提醒学生看什么。"},
                    },
                    "required": ["parameter", "from", "to"],
                },
            },
        },
        "required": ["title", "given", "points"],
    }


class DrawFigureTool(BaseTool):
    name = "draw_figure"
    description = (
        "在右侧打开一个可拖动、会动的图示（平面直角坐标系）。"
        "学生明确要求画图/可视化，或题目里有坐标、函数、面积、参数变化这类"
        "看图更容易懂的关系时调用；学生卡住时先问一句要不要看图，同意了再调用。"
        "点坐标与观察值都写成算式，可以用参数名、点坐标（如 C.x）和 sqrt 等函数；"
        "需要展示“拖动时怎么变”时给出 parameters 与 trajectory。"
        "调用后只用一两句话说明该看什么，不要复述图中的数值。"
    )
    running_label = "正在画图…"
    input_schema: dict[str, Any] = figure_input_schema()

    async def execute(self, input: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            spec = FigureSpec.model_validate(input)
        except ValidationError as exc:
            return ToolResult(
                content=ctx.reminders.text("figure_invalid", error=_validation_message(exc)),
                is_error=True,
                status_label="画图失败",
            )

        payload = spec.model_dump(mode="json", by_alias=True)
        payload["kind"] = "figure"
        return ToolResult(
            content=json.dumps(
                {"shown": True, "title": spec.title}, ensure_ascii=False
            )
            + "\n"
            + ctx.reminders.text("figure_shown"),
            status_label="图已打开",
            display=payload,
        )


draw_figure = DrawFigureTool()
