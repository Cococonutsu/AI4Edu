"""`QueryEngine` 的回合行为与按步骤的 thinking 控制。"""

from __future__ import annotations

from pathlib import Path

import pytest

import ai4edu.tools.analyze_problem as analyze_problem_module
from ai4edu.config import Settings
from ai4edu.core.events import AgentError, TextDelta, TurnFinished
from ai4edu.core.query_engine import QueryEngine
from ai4edu.models.content import TextBlock, ToolResultBlock, ToolUseBlock
from ai4edu.models.messages import Message, validate_messages
from ai4edu.models.web import WebSearchHit
from ai4edu.prompts import load_reminders
from ai4edu.storage.repos import llm_calls as llm_calls_repo
from ai4edu.storage.repos import problems
from ai4edu.tools.base import ToolResult
from ai4edu.tools.record_diagnosis import record_diagnosis
from ai4edu.tutoring.framework import load_config
from ai4edu.tutoring.policy import start_problem
from ai4edu.tutoring.problem import ProblemModel
from ai4edu.tutoring.state import Phase, TutorState
from fakes import FakeProvider, FakeResponse, FakeWebTools

pytestmark = pytest.mark.asyncio

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"

PROBLEM = {
    "statement": "反比例函数综合题",
    "grade_band": "junior",
    "domain": "function_geometry",
    "givens": ["C 为 OA 中点"],
    "goal": "求 k",
    "answer": {"text": "k = 5", "latex": "k=5"},
    "relations": [
        {"id": "R1", "kind": "element", "text": "设 C(a, k/a)"},
    ],
    "subtasks": [
        {
            "id": "T1",
            "stage": "represent",
            "title": "坐标表征",
            "goal": "写出 C 的坐标",
            "required_relations": ["R1"],
            "completion_criteria": "给出 C(a,k/a)",
            "optional": False,
        }
    ],
    "reference_solution": "略",
}


@pytest.fixture(scope="module")
def config():
    return load_config(CONFIG_DIR)


@pytest.fixture(scope="module")
def reminders():
    return load_reminders(CONFIG_DIR)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        config_dir=CONFIG_DIR,
        deepseek_api_key="",
    )


def _engine(
    settings, config, reminders, provider, session_factory, web=None
) -> QueryEngine:
    return QueryEngine(
        settings=settings,
        config=config,
        reminders=reminders,
        provider=provider,
        web=web,
        session_factory=session_factory,
    )


async def _collect(engine: QueryEngine, user, conversation_id: int, text: str = "题目"):
    return [
        event
        async for event in engine.run_turn(
            user=user,
            conversation_id=conversation_id,
            text=text,
            attachment_ids=[],
        )
    ]


def _text_of(message: Message) -> str:
    return "".join(
        block.text for block in message.content if isinstance(block, TextBlock)
    )


def _tool_result_text(message: Message) -> str:
    return "".join(
        block.content
        for block in message.content
        if isinstance(block, ToolResultBlock)
    )


async def test_no_diagnosis_right_after_analyze(
    seed, session_factory, monkeypatch, config, reminders, settings
):
    """回归：错误记录 #3 —— 读完新题后开场白说了两遍。"""

    user, conversation_id = await seed()

    async def fake_execute(input, ctx):
        problem = ProblemModel.model_validate(PROBLEM)
        record = await ctx.store.add_problem(
            model_json=problem.model_dump(mode="json"),
            confidence="verified",
            framework_version=ctx.config.framework.version,
        )
        await ctx.store.commit()
        ctx.problem = problem
        await ctx.persist_state(start_problem(problem, record.id, ctx.config))
        return ToolResult(content='{"ok": true}', status_label="题目分析完成")

    monkeypatch.setattr(
        analyze_problem_module.analyze_problem, "execute", fake_execute
    )
    provider = FakeProvider(
        [
            FakeResponse(
                tool_calls=[
                    (
                        "call_analyze",
                        "analyze_problem",
                        '{"problem_text": "反比例函数综合题"}',
                    )
                ]
            ),
            FakeResponse(text=["我们先看第一问：C 的坐标怎么表示？"]),
        ]
    )

    events = await _collect(
        _engine(settings, config, reminders, provider, session_factory),
        user,
        conversation_id,
    )

    assert any(isinstance(event, TextDelta) for event in events)
    assert "record_diagnosis" not in provider.tool_names(1)
    assert "analyze_problem" in provider.tool_names(0)


async def test_reminder_after_text_already_sent(
    seed, session_factory, monkeypatch, config, reminders, settings
):
    """回归：错误记录 #4 —— 回合内已发给学生的正文被改写重发。"""

    state = TutorState(phase=Phase.completed)
    user, conversation_id = await seed(
        phase="completed", state_json=state.to_json()
    )

    async def fake_execute(input, ctx):
        return ToolResult(content='{"ok": true}', status_label="完成")

    monkeypatch.setattr(record_diagnosis, "execute", fake_execute)
    provider = FakeProvider(
        [
            FakeResponse(
                text=["我先记一下你的思路。"],
                tool_calls=[("call_check", "record_diagnosis", "{}")],
            ),
            FakeResponse(text=["补充一句：注意符号。"]),
        ]
    )

    await _collect(
        _engine(settings, config, reminders, provider, session_factory),
        user,
        conversation_id,
        text="1+1=2",
    )

    assert len(provider.requests) == 2
    last_message = provider.messages(1)[-1]
    assert last_message.role == "user"
    assert "已经对学生说过" in _text_of(last_message)


async def test_point_question_reply_streams_without_tools(
    seed, session_factory, config, reminders, settings
):
    """点问题直接写正文：一次调用、正文即时下发、不调用工具。"""

    user, conversation_id = await seed()
    reply = "求根公式是 $x=\\frac{-b\\pm\\sqrt{b^2-4ac}}{2a}$。"
    provider = FakeProvider([FakeResponse(text=[reply])])

    events = await _collect(
        _engine(settings, config, reminders, provider, session_factory),
        user,
        conversation_id,
        text="求根公式是什么",
    )

    visible_text = "".join(
        event.text for event in events if isinstance(event, TextDelta)
    )
    assert len(provider.requests) == 1
    assert visible_text == reply
    assert provider.tool_names(0) == [
        "analyze_problem",
        "draw_figure",
        "web_search",
        "web_fetch",
    ]
    finished = [event for event in events if isinstance(event, TurnFinished)]
    assert finished[-1].status == "complete"


async def test_tutoring_interjection_reply_is_not_discarded(
    seed, session_factory, config, reminders, settings
):
    """回归：错误记录 #18 —— 辅导中插问的正文被守卫丢弃重试。

    插问（"△是什么意思"）不需要工具；守卫只重试"既没有正文也没有工具调用"的空步。
    """

    state = TutorState(phase=Phase.tutoring)
    user, conversation_id = await seed(
        phase="tutoring", state_json=state.to_json()
    )
    provider = FakeProvider([FakeResponse(text=["△表示三角形。"])])

    events = await _collect(
        _engine(settings, config, reminders, provider, session_factory),
        user,
        conversation_id,
        text="△是什么意思",
    )

    assert len(provider.requests) == 1
    assert "".join(
        event.text for event in events if isinstance(event, TextDelta)
    ) == "△表示三角形。"
    assert not [event for event in events if isinstance(event, AgentError)]


async def test_empty_step_is_retried_with_reminder(
    seed, session_factory, config, reminders, settings
):
    """只有思考、没有正文也没有工具调用的一步：追加提醒后重试。"""

    user, conversation_id = await seed()
    provider = FakeProvider(
        [FakeResponse(thinking=["想一想……"]), FakeResponse(text=["你好！"])]
    )

    events = await _collect(
        _engine(settings, config, reminders, provider, session_factory),
        user,
        conversation_id,
        text="你好",
    )

    assert len(provider.requests) == 2
    assert "没有对学生说任何话" in _text_of(provider.messages(1)[-1])
    assert "".join(
        event.text for event in events if isinstance(event, TextDelta)
    ) == "你好！"


async def test_every_request_is_a_valid_sequence(
    seed, session_factory, monkeypatch, config, reminders, settings
):
    """每次模型请求的消息序列都必须合法（含数据库里的残缺历史）。"""

    async def fake_execute(input, ctx):
        return ToolResult(content='{"ok": true}', status_label="完成")

    monkeypatch.setattr(record_diagnosis, "execute", fake_execute)

    state = TutorState(phase=Phase.completed)
    user, conversation_id = await seed(
        phase="completed", state_json=state.to_json()
    )
    provider = FakeProvider(
        [
            FakeResponse(
                tool_calls=[("call_a", "record_diagnosis", "{}")]
            ),
            FakeResponse(
                tool_calls=[("call_b", "record_diagnosis", "{}")]
            ),
            FakeResponse(text=["好的，我们继续。"]),
        ]
    )

    await _collect(
        _engine(settings, config, reminders, provider, session_factory),
        user,
        conversation_id,
    )

    assert len(provider.requests) == 3
    for request in provider.requests:
        validate_messages(list(request.messages))

    # 数据库里的残缺历史：assistant 有 tool_use，但上一回合在工具执行中被停止。
    user2, conversation_id2 = await seed(
        phase="completed", state_json=state.to_json()
    )
    async with session_factory() as db:
        from ai4edu.session.store import TurnStore

        store = TurnStore(db, user_id=user2.id, conversation_id=conversation_id2)
        await store.append_messages(
            [
                Message(
                    role="user",
                    content=[TextBlock(text="上一题")],
                    turn_id="old-turn",
                ),
                Message(
                    role="assistant",
                    content=[
                        ToolUseBlock(id="call_old", name="record_diagnosis", input={})
                    ],
                    turn_id="old-turn",
                ),
            ]
        )
        await store.commit()

    provider2 = FakeProvider([FakeResponse(text=["我们接着看。"])])
    await _collect(
        _engine(settings, config, reminders, provider2, session_factory),
        user2,
        conversation_id2,
        text="继续",
    )

    assert provider2.requests
    for request in provider2.requests:
        validate_messages(list(request.messages))


async def test_empty_turn_shows_error(
    seed, session_factory, config, reminders, settings
):
    """回归：错误记录 #6 —— 读题失败后学生页面一片空白。"""

    state = TutorState(phase=Phase.completed)
    user, conversation_id = await seed(
        phase="completed", state_json=state.to_json()
    )
    # 只有思考，没有正文，也没有工具调用。
    provider = FakeProvider([FakeResponse(thinking=["我再想想……"])])

    events = await _collect(
        _engine(settings, config, reminders, provider, session_factory),
        user,
        conversation_id,
        text="这道题怎么做",
    )

    errors = [event for event in events if isinstance(event, AgentError)]
    finished = [event for event in events if isinstance(event, TurnFinished)]
    assert errors
    assert finished and finished[-1].status == "error"


async def test_thinking_turns_off_after_diagnosis_and_steps_are_logged(
    seed, session_factory, monkeypatch, config, reminders, settings
):
    """诊断步骤开思考、写回复的步骤关思考；llm_calls 记录 step 与 thinking。"""

    import ai4edu.tools.record_diagnosis as record_diagnosis_module

    state = TutorState(phase=Phase.tutoring)
    user, conversation_id = await seed(
        phase="tutoring", state_json=state.to_json()
    )

    async def fake_execute(input, ctx):
        return ToolResult(content='{"action": "elicit_evidence"}', status_label="好了")

    monkeypatch.setattr(
        record_diagnosis_module.record_diagnosis, "execute", fake_execute
    )
    provider = FakeProvider(
        [
            FakeResponse(
                tool_calls=[
                    (
                        "call_diag",
                        "record_diagnosis",
                        '{"subtask_id": "T1", "evidence_quotes": [], '
                        '"solo_level": "SU", "math_status": "unverified", '
                        '"gaps": [], "completion_met": false, '
                        '"made_progress": false, '
                        '"student_requested_help": false, '
                        '"prior_support_level": "L0", "rationale": "略"}',
                    )
                ]
            ),
            FakeResponse(text=["能说说你为什么这样想吗？"]),
        ]
    )

    events = await _collect(
        _engine(settings, config, reminders, provider, session_factory),
        user,
        conversation_id,
        text="我不会",
    )

    assert any(isinstance(event, TextDelta) for event in events)
    assert len(provider.requests) == 2
    assert provider.requests[0].thinking == "on"
    assert provider.requests[1].thinking == "off"

    async with session_factory() as db:
        rows = await llm_calls_repo.list_for_conversation(
            db, conversation_id, user.id
        )
    tutor_rows = [row for row in rows if row.purpose == "tutor"]
    assert [(row.step, row.thinking) for row in tutor_rows] == [
        (1, "on"),
        (2, "off"),
    ]


async def test_tutor_requests_enough_tokens(
    seed, session_factory, config, reminders, settings
):
    """回归：错误记录 #7 —— 读题那一步要输出思考 + 完整题目模型，8192 会被截断。"""

    user, conversation_id = await seed()
    provider = FakeProvider([FakeResponse(text=["你好"])])

    await _collect(
        _engine(settings, config, reminders, provider, session_factory),
        user,
        conversation_id,
        text="你好",
    )

    assert provider.requests[0].max_tokens >= 16384


async def test_figure_display_is_streamed_and_kept_in_history(
    seed, session_factory, monkeypatch, config, reminders, settings
):
    """draw_figure 的图要发给浏览器，并在刷新会话后仍挂在那条消息上。"""

    import ai4edu.tools.figure as figure_module

    figure = {"kind": "figure", "title": "拖一拖", "points": []}

    async def fake_execute(input, ctx):
        return ToolResult(
            content='{"shown": true}', status_label="图已打开", display=figure
        )

    monkeypatch.setattr(figure_module.draw_figure, "execute", fake_execute)
    user, conversation_id = await seed()
    provider = FakeProvider(
        [
            FakeResponse(
                tool_calls=[("call_fig", "draw_figure", '{"title": "拖一拖", "points": []}')]
            ),
            FakeResponse(text=["图已经打开了，拖拖看。"]),
        ]
    )

    from ai4edu.core.events import ToolDisplay
    from ai4edu.server.serializers import visible_messages
    from ai4edu.storage.repos import conversations as conversations_repo

    events = await _collect(
        _engine(settings, config, reminders, provider, session_factory),
        user,
        conversation_id,
        text="画个图看看",
    )

    displays = [event for event in events if isinstance(event, ToolDisplay)]
    assert displays and displays[0].kind == "figure"

    async with session_factory() as db:
        rows = await conversations_repo.get(db, conversation_id, user.id)
        assert rows is not None
        from ai4edu.storage.repos import messages as messages_repo

        message_rows = await messages_repo.list_for_conversation(db, conversation_id, user.id)
    visible = visible_messages(message_rows)
    assert [item.figures for item in visible if item.role == "assistant"] == [[figure]]


async def test_web_search_result_is_sent_to_the_next_model_request(
    seed, session_factory, config, reminders, settings
):
    """联网搜索结果进入后续模型请求，并在本回合内可用。"""

    user, conversation_id = await seed()
    fake_web = FakeWebTools(
        hits=[
            WebSearchHit(
                title="2026 年世界杯",
                url="https://example.com/world-cup",
                snippet="短摘要",
                summary="2026 年世界杯的举办地信息。",
                site_name="示例站",
                date="2026-07-01",
                rerank_score=2.5,
                authority=3,
            )
        ]
    )
    provider = FakeProvider(
        [
            FakeResponse(
                tool_calls=[
                    (
                        "call_search",
                        "web_search",
                        '{"query": "2026 年世界杯举办地", "count": 3}',
                    )
                ]
            ),
            FakeResponse(text=["老师查了资料，我们一起看看。"]),
        ]
    )

    events = await _collect(
        _engine(
            settings,
            config,
            reminders,
            provider,
            session_factory,
            web=fake_web,
        ),
        user,
        conversation_id,
        text="2026 年世界杯在哪里举办",
    )

    assert fake_web.searches == [("2026 年世界杯举办地", 3)]
    assert len(provider.requests) == 2
    result_text = _tool_result_text(provider.messages(1)[-1])
    assert "2026 年世界杯" in result_text
    assert "https://example.com/world-cup" in result_text
    assert "2.5/3" in result_text
    assert reminders.text("after_web_search") in result_text
    assert any(isinstance(event, TextDelta) for event in events)


async def test_web_tools_unavailable_reaches_the_model(
    seed, session_factory, config, reminders, tmp_path
):
    """没有配置密钥时 web_search 返回“未开通”错误结果，模型据此继续辅导。"""

    user, conversation_id = await seed()
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        config_dir=CONFIG_DIR,
        deepseek_api_key="",
    )
    provider = FakeProvider(
        [
            FakeResponse(
                tool_calls=[
                    ("call_search", "web_search", '{"query": "某个事实"}')
                ]
            ),
            FakeResponse(text=["老师暂时查不了网，我们先按课本知识来。"]),
        ]
    )

    await _collect(
        _engine(settings, config, reminders, provider, session_factory),
        user,
        conversation_id,
        text="帮我查一下这个事实",
    )

    result_text = _tool_result_text(provider.messages(1)[-1])
    assert reminders.text("web_tools_unavailable") in result_text
