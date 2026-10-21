"""`DeepSeekWebTools`：请求格式、响应映射、错误分类与工厂。"""

from __future__ import annotations

import json

import httpx
import pytest

from ai4edu.config import Settings
from ai4edu.tools.web.client import DeepSeekWebTools, WebToolsError, make_web_tools

pytestmark = pytest.mark.asyncio


def _tools(handler, *, base_url: str = "https://api.test") -> DeepSeekWebTools:
    return DeepSeekWebTools(
        "test-key",
        base_url=base_url,
        transport=httpx.MockTransport(handler),
    )


async def test_search_maps_results_and_sends_expected_body():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/tools/search"
        assert request.headers["authorization"] == "Bearer test-key"
        assert json.loads(request.content) == {"query": "勾股定理", "count": 3}
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "勾股定理",
                        "url": "https://example.com/pythagoras",
                        "snippet": "短摘要",
                        "summary": "长摘要：直角三角形两直角边的平方和……",
                        "site_name": "维基百科",
                        "date": "2026-01-01T00:00:00Z",
                        "rerank_score": 2.75,
                        "authority": 4,
                    },
                    {
                        "title": "缺少可选字段的结果",
                        "url": "https://example.com/other",
                        "snippet": "短摘要",
                        "summary": "长摘要",
                        "site_name": None,
                        "date": None,
                        "rerank_score": 1,
                        "authority": -1,
                    },
                ]
            },
        )

    hits = await _tools(handler).search("勾股定理", count=3)

    assert len(hits) == 2
    first = hits[0]
    assert first.title == "勾股定理"
    assert first.url == "https://example.com/pythagoras"
    assert first.snippet == "短摘要"
    assert first.summary.startswith("长摘要")
    assert first.site_name == "维基百科"
    assert first.date == "2026-01-01T00:00:00Z"
    assert first.rerank_score == 2.75
    assert first.authority == 4

    second = hits[1]
    assert second.site_name is None
    assert second.date is None
    assert second.rerank_score == 1.0
    assert second.authority == -1


async def test_search_tolerates_missing_fields_and_empty_results():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{}]})

    hits = await _tools(handler).search("x")

    assert len(hits) == 1
    assert hits[0].title == ""
    assert hits[0].url == ""
    assert hits[0].snippet == ""
    assert hits[0].summary == ""
    assert hits[0].site_name is None
    assert hits[0].date is None
    assert hits[0].rerank_score == 0.0
    assert hits[0].authority == 0

    def empty_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    assert await _tools(empty_handler).search("x") == []


async def test_fetch_maps_page_and_sends_expected_body():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/tools/fetch"
        assert json.loads(request.content) == {"url": "https://example.com/a"}
        return httpx.Response(
            200, json={"title": "某页面", "content": "# 正文\n\n内容"}
        )

    page = await _tools(handler).fetch("https://example.com/a")

    assert page.title == "某页面"
    assert page.content == "# 正文\n\n内容"


@pytest.mark.parametrize(
    ("status", "recoverable"),
    [(408, True), (409, True), (429, True), (500, True), (502, True), (503, True), (504, True), (400, False), (404, False)],
)
async def test_http_status_maps_recoverable(status: int, recoverable: bool):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status, json={"error": {"message": "服务返回了错误"}}
        )

    with pytest.raises(WebToolsError) as info:
        await _tools(handler).search("x")

    assert info.value.recoverable is recoverable
    assert str(info.value) == "服务返回了错误"


async def test_http_error_without_json_falls_back_to_status_text():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="not json")

    with pytest.raises(WebToolsError) as info:
        await _tools(handler).fetch("https://example.com/a")

    assert info.value.recoverable is False
    assert "400" in str(info.value)


async def test_402_reports_insufficient_balance():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={"error": {"message": "余额为零"}})

    with pytest.raises(WebToolsError) as info:
        await _tools(handler).search("x")

    assert info.value.recoverable is False
    assert "账户余额不足" in str(info.value)
    assert "余额为零" in str(info.value)


async def test_timeout_and_transport_errors_are_recoverable():
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("读超时", request=request)

    with pytest.raises(WebToolsError) as info:
        await _tools(timeout_handler).search("x")

    assert info.value.recoverable is True
    assert "网络错误" in str(info.value)

    def transport_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("连不上", request=request)

    with pytest.raises(WebToolsError) as info2:
        await _tools(transport_handler).fetch("https://example.com/a")

    assert info2.value.recoverable is True
    assert "网络错误" in str(info2.value)


async def test_base_url_ending_with_v1_is_normalized():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json={"results": []})

    tools = _tools(handler, base_url="https://api.test/v1/")
    assert await tools.search("x") == []
    assert seen == ["/v1/tools/search"]


async def test_make_web_tools_returns_none_without_key(tmp_path):
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        deepseek_api_key="",
    )

    assert make_web_tools(settings) is None


async def test_make_web_tools_builds_client_with_key(tmp_path):
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        deepseek_api_key="sk-test",
        deepseek_base_url="https://api.deepseek.com/v1",
    )

    tools = make_web_tools(settings)

    assert isinstance(tools, DeepSeekWebTools)
