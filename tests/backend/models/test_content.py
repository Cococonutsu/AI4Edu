"""内容块与工具结果内容的 JSON 互转、富内容渲染。"""

from __future__ import annotations

from ai4edu.models.content import (
    ToolResultBlock,
    block_from_json,
    block_to_json,
    tool_result_text,
)


def test_tool_result_text_passthrough_for_plain_string():
    assert tool_result_text("第一条结果") == "第一条结果"


def test_tool_result_text_joins_rich_blocks():
    content = [
        {"type": "text", "text": "标题：勾股定理"},
        {"type": "text", "text": "链接：https://example.com"},
    ]

    assert tool_result_text(content) == "标题：勾股定理\n链接：https://example.com"


def test_tool_result_text_renders_block_without_text_as_json():
    content = [{"type": "data", "value": 42}]

    rendered = tool_result_text(content)

    assert '"value": 42' in rendered


def test_tool_result_block_round_trips_rich_content():
    block = ToolResultBlock(
        tool_use_id="call_1",
        content=[{"type": "text", "text": "富内容"}],
        is_error=True,
        status_label="失败",
    )

    data = block_to_json(block)
    assert data["content"] == [{"type": "text", "text": "富内容"}]
    assert data["is_error"] is True

    restored = block_from_json(data)
    assert isinstance(restored, ToolResultBlock)
    assert restored.content == [{"type": "text", "text": "富内容"}]
    assert restored.is_error is True


def test_tool_result_block_reads_legacy_string_content():
    restored = block_from_json(
        {
            "type": "tool_result",
            "tool_use_id": "call_1",
            "content": "旧数据纯文本",
            "is_error": False,
            "status_label": "",
        }
    )

    assert isinstance(restored, ToolResultBlock)
    assert restored.content == "旧数据纯文本"
    assert tool_result_text(restored.content) == "旧数据纯文本"
