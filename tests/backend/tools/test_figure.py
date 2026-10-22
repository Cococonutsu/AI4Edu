"""`draw_figure`：图形描述的结构校验与下发数据。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai4edu.prompts import Reminders
from ai4edu.tools.figure import FigureSpec, draw_figure
from ai4edu.tutoring.state import TutorState

pytestmark = pytest.mark.asyncio


FIGURE = {
    "title": "拖动 A 点，看面积怎么变",
    "given": ["C 为 OA 中点", "C、D 在 y=k/x 上", "CE⊥x 轴"],
    "unknowns": ["a", "b"],
    "caption": "注意 S△BDE 与 k 的比值。",
    "parameters": [
        {"name": "a", "label": "a（A 的横坐标）", "value": 4, "min": 1, "max": 9},
        {"name": "b", "label": "b（A 的纵坐标）", "value": 4, "min": 1, "max": 9},
    ],
    "points": [
        {"id": "O", "x": "0", "y": "0"},
        {"id": "A", "x": "a", "y": "b", "role": "highlight"},
        {"id": "C", "x": "a/2", "y": "b/2"},
        {"id": "B", "x": "a", "y": "0"},
        {"id": "E", "x": "a/2", "y": "0"},
        {"id": "D", "x": "a", "y": "(a*b/4)/a"},
    ],
    "segments": [
        {"from": "O", "to": "A"},
        {"from": "O", "to": "B"},
        {"from": "C", "to": "E", "dashed": True},
    ],
    "polygons": [{"points": ["B", "D", "E"]}],
    "curves": [{"expression": "(a*b/4)/x", "from": 0.5, "to": 9}],
    "readouts": [
        {"label": "k", "expression": "a*b/4"},
        {"label": "S△BDE ÷ k", "expression": "(a/2)*((a*b/4)/a)/2/(a*b/4)", "format": "fraction"},
    ],
    "trajectory": [
        {"parameter": "a", "from": 4, "to": 7, "seconds": 4, "note": "拖动 A 点，看看比值"},
    ],
}


def _ctx(reminders):
    return SimpleNamespace(
        reminders=reminders, state=TutorState.idle(), problem=None
    )


async def test_figure_is_returned_for_the_browser():
    reminders = Reminders()

    result = await draw_figure.execute(FIGURE, _ctx(reminders))

    assert result.is_error is False, result.content
    assert result.display is not None
    assert result.display["kind"] == "figure"
    assert result.display["title"] == FIGURE["title"]
    # 轨迹的下划线字段在线上用 from 表达。
    assert result.display["trajectory"][0]["from"] == 4
    # 给模型的结果只说"已打开"，不复述整张图。
    assert "已打开" in result.content
    assert "readouts" not in result.content


async def test_unknown_name_is_rejected_with_reason():
    reminders = Reminders()
    broken = dict(FIGURE)
    broken["readouts"] = [{"label": "面积", "expression": "S_BDE"}]

    result = await draw_figure.execute(broken, _ctx(reminders))

    assert result.is_error is True
    assert "S_BDE" in result.content


async def test_bad_reference_is_rejected():
    reminders = Reminders()
    broken = dict(FIGURE)
    broken["segments"] = [{"from": "O", "to": "Z"}]

    result = await draw_figure.execute(broken, _ctx(reminders))

    assert result.is_error is True
    assert "Z" in result.content


async def test_expression_charset_is_limited():
    reminders = Reminders()
    broken = dict(FIGURE)
    broken["readouts"] = [{"label": "x", "expression": "__import__('os')"}]

    result = await draw_figure.execute(broken, _ctx(reminders))

    assert result.is_error is True


async def test_point_coordinate_needs_existing_point():
    reminders = Reminders()
    # 参数名可以直接用作坐标。
    minimal = {"title": "看 A 点", "given": ["A 在第一象限"], "parameters": FIGURE["parameters"], "points": [
        {"id": "A", "x": "a", "y": "b"}
    ]}
    assert FigureSpec.model_validate(minimal).points[0].id == "A"

    # 引用不存在的点坐标要报错。
    broken = {**minimal, "readouts": [{"label": "x", "expression": "Q.x"}]}
    result = await draw_figure.execute(broken, _ctx(reminders))
    assert result.is_error is True
    assert "Q.x" in result.content


async def test_circle_accepts_radius_expression():
    """回归 #22：圆可以按半径算式画，也必须二选一地给出 through 或 radius。"""

    reminders = Reminders()
    figure = {
        "title": "圆",
        "given": ["圆心在 y 轴上"],
        "parameters": [{"name": "m", "value": 0}],
        "points": [{"id": "C", "x": "0", "y": "m"}],
        "circles": [{"center": "C", "radius": "sqrt(m^2+12)"}],
    }

    result = await draw_figure.execute(figure, _ctx(reminders))
    assert result.is_error is False, result.content
    assert result.display is not None
    assert result.display["circles"][0]["radius"] == "sqrt(m^2+12)"

    missing = {**figure, "circles": [{"center": "C"}]}
    assert (await draw_figure.execute(missing, _ctx(reminders))).is_error is True

    unknown = {**figure, "circles": [{"center": "C", "radius": "zz"}]}
    assert (await draw_figure.execute(unknown, _ctx(reminders))).is_error is True



async def test_figure_needs_given_conditions():
    """回归 #23：题目还没确定图形时（如求圆的方程）不能凭空画一个“当作已知”的图。

    工具要求先列出图依据的已知条件；列不出来就拒绝，并告诉模型先用文字引导。
    """

    reminders = Reminders()
    no_given = {k: v for k, v in FIGURE.items() if k != "given"}

    result = await draw_figure.execute(no_given, _ctx(reminders))

    assert result.is_error is True
    assert "given" in result.content
    assert "不要调用 draw_figure" in result.content


async def test_unknowns_must_be_parameters():
    reminders = Reminders()
    broken = {**FIGURE, "unknowns": ["D"]}

    result = await draw_figure.execute(broken, _ctx(reminders))

    assert result.is_error is True
    assert "D" in result.content


async def test_given_and_unknowns_reach_the_browser():
    reminders = Reminders()

    result = await draw_figure.execute(FIGURE, _ctx(reminders))

    assert result.is_error is False, result.content
    assert result.display is not None
    assert result.display["given"] == FIGURE["given"]
    assert result.display["unknowns"] == ["a", "b"]


async def test_given_must_not_contain_derivations():
    """回归 #23：given 是条件清单，写进推导结论等于泄露答案。"""

    reminders = Reminders()
    leaking = {**FIGURE, "given": ["圆心在 y 轴上 ⇒ 圆心为 (0, −E/2)，即 D=0"]}

    result = await draw_figure.execute(leaking, _ctx(reminders))

    assert result.is_error is True
    assert "已知条件" in result.content
