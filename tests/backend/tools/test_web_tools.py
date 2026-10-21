"""`web_search` / `web_fetch`：参数校验、结果排版、截断与错误文案。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from ai4edu.models.web import WebFetchPage, WebSearchHit, WebToolsError
from ai4edu.prompts import load_reminders
from ai4edu.tools.registry import tools_for
from ai4edu.tools.web_fetch import web_fetch
from ai4edu.tools.web_search import web_search
from ai4edu.tutoring.state import Phase
from fakes import FakeWebTools

pytestmark = pytest.mark.asyncio

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


@pytest.fixture(scope="module")
def reminders():
    return load_reminders(CONFIG_DIR)


def _ctx(reminders, web):
    return SimpleNamespace(reminders=reminders, web=web)


def _hit(**overrides) -> WebSearchHit:
    values = {
        "title": "勾股定理",
        "url": "https://example.com/pythagoras",
        "snippet": "短摘要",
        "summary": "长摘要：直角三角形两直角边的平方和等于斜边的平方。",
        "site_name": "维基百科",
        "date": "2026-01-01",
        "rerank_score": 2.34,
        "authority": 4,
    }
    values.update(overrides)
    return WebSearchHit(**values)


# ---- web_search ----


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"query": 123},
        {"query": "   "},
        {"query": "a" * 129},
    ],
)
async def test_search_rejects_bad_query(reminders, payload):
    fake = FakeWebTools()

    result = await web_search.execute(payload, _ctx(reminders, fake))

    assert result.is_error is True
    assert fake.searches == []


@pytest.mark.parametrize("count", ["5", 2.5, True, None])
async def test_search_rejects_non_integer_count(reminders, count):
    fake = FakeWebTools()

    result = await web_search.execute(
        {"query": "勾股定理", "count": count}, _ctx(reminders, fake)
    )

    assert result.is_error is True
    assert fake.searches == []


async def test_search_clamps_count_to_one_through_ten(reminders):
    low = FakeWebTools()
    await web_search.execute(
        {"query": "勾股定理", "count": 0}, _ctx(reminders, low)
    )
    assert low.searches == [("勾股定理", 1)]

    high = FakeWebTools()
    await web_search.execute(
        {"query": "勾股定理", "count": 99}, _ctx(reminders, high)
    )
    assert high.searches == [("勾股定理", 10)]


async def test_search_without_web_tools_reports_unavailable(reminders):
    result = await web_search.execute(
        {"query": "勾股定理"}, _ctx(reminders, None)
    )

    assert result.is_error is True
    assert result.content == reminders.text("web_tools_unavailable")


async def test_search_error_text_contains_reason(reminders):
    fake = FakeWebTools(
        error=WebToolsError("搜索服务超时", recoverable=True)
    )

    result = await web_search.execute(
        {"query": "勾股定理"}, _ctx(reminders, fake)
    )

    assert result.is_error is True
    assert "联网搜索没有成功" in result.content
    assert "搜索服务超时" in result.content


async def test_search_success_formats_results_for_the_model(reminders):
    fake = FakeWebTools(
        hits=[
            _hit(),
            _hit(
                title="第二个结果",
                url="https://example.com/other",
                summary="第二个长摘要",
                site_name=None,
                date=None,
                rerank_score=1.0,
                authority=-1,
            ),
        ]
    )

    result = await web_search.execute(
        {"query": "勾股定理", "count": 2}, _ctx(reminders, fake)
    )

    assert result.is_error is False
    assert result.display is None
    assert result.status_label == "已搜索到 2 条结果"
    assert fake.searches == [("勾股定理", 2)]
    content = result.content
    assert content.startswith(
        "联网搜索「勾股定理」完成，共 2 条结果（只有老师可见）：\n\n"
    )
    assert "1. 勾股定理（维基百科，2026-01-01）" in content
    assert "链接：https://example.com/pythagoras" in content
    assert "摘要：长摘要：直角三角形两直角边的平方和等于斜边的平方。" in content
    assert "（相关度 2.3/3，权威度 4/4）" in content
    assert "2. 第二个结果（未知站点，日期未知）" in content
    assert "（相关度 1.0/3，权威度 -1/4）" in content
    assert "\n\n2. " in content
    assert content.endswith(reminders.text("after_web_search"))


async def test_search_empty_results_has_retry_hint(reminders):
    fake = FakeWebTools(hits=[])

    result = await web_search.execute(
        {"query": "很冷门的关键词"}, _ctx(reminders, fake)
    )

    assert result.is_error is False
    assert result.display is None
    assert result.content == (
        "联网搜索「很冷门的关键词」没有找到相关结果。"
        "可以换更短、更具体的关键词重试，或基于课本知识继续辅导。"
    )


# ---- web_fetch ----


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"url": 123},
        {"url": "   "},
        {"url": "ftp://example.com/a"},
        {"url": "https:///no-host"},
        {"url": "https://user:pass@example.com/a"},
        {"url": "https://user@example.com/a"},
        {"url": "https://example.com/" + "a" * 8192},
    ],
)
async def test_fetch_rejects_bad_url(reminders, payload):
    fake = FakeWebTools()

    result = await web_fetch.execute(payload, _ctx(reminders, fake))

    assert result.is_error is True
    assert fake.fetched == []


async def test_fetch_without_web_tools_reports_unavailable(reminders):
    result = await web_fetch.execute(
        {"url": "https://example.com/a"}, _ctx(reminders, None)
    )

    assert result.is_error is True
    assert result.content == reminders.text("web_tools_unavailable")


async def test_fetch_error_text_contains_reason(reminders):
    fake = FakeWebTools(
        error=WebToolsError("抓取超时", recoverable=True)
    )

    result = await web_fetch.execute(
        {"url": "https://example.com/a"}, _ctx(reminders, fake)
    )

    assert result.is_error is True
    assert "网页抓取没有成功" in result.content
    assert "抓取超时" in result.content


async def test_fetch_success_returns_page_content(reminders):
    fake = FakeWebTools(
        page=WebFetchPage(title="某页面", content="# 正文\n\n这是网页内容。")
    )

    result = await web_fetch.execute(
        {"url": "https://example.com/a"}, _ctx(reminders, fake)
    )

    assert result.is_error is False
    assert result.display is None
    assert result.status_label == "网页已读取"
    assert fake.fetched == ["https://example.com/a"]
    content = result.content
    assert content.startswith("已读取网页「某页面」（只有老师可见）：\n\n")
    assert "# 正文\n\n这是网页内容。" in content
    assert content.endswith(reminders.text("after_web_fetch"))


async def test_fetch_truncates_long_content(reminders):
    fake = FakeWebTools(
        page=WebFetchPage(title="长页面", content="字" * 25_000)
    )

    result = await web_fetch.execute(
        {"url": "https://example.com/a"}, _ctx(reminders, fake)
    )

    assert result.is_error is False
    assert "字" * 20_000 in result.content
    assert "字" * 20_001 not in result.content
    assert "（正文过长，已截断）" in result.content
    assert len(result.content) < 25_000


# ---- registry ----


@pytest.mark.parametrize(
    "phase", [Phase.idle, Phase.tutoring, Phase.extension, Phase.completed]
)
async def test_every_phase_offers_web_tools(phase):
    names = [tool.name for tool in tools_for(phase)]

    assert names[-2:] == ["web_search", "web_fetch"]
