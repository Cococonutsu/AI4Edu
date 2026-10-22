"""usage 解析：缓存命中的三种厂商字段形态与缺省。"""

from __future__ import annotations

from types import SimpleNamespace

from ai4edu.api.openai_compat import _usage_from_response


def test_reads_openai_style_prompt_tokens_details():
    usage = SimpleNamespace(
        prompt_tokens=100,
        completion_tokens=20,
        prompt_tokens_details=SimpleNamespace(cached_tokens=88),
    )

    parsed = _usage_from_response(usage)

    assert parsed.cached_tokens == 88
    assert parsed.input_tokens == 100
    assert parsed.output_tokens == 20


def test_reads_deepseek_style_cache_hit_field():
    usage = SimpleNamespace(
        prompt_tokens=100,
        completion_tokens=20,
        prompt_cache_hit_tokens=64,
        prompt_cache_miss_tokens=36,
    )

    assert _usage_from_response(usage).cached_tokens == 64


def test_reads_plain_cached_tokens_field():
    usage = SimpleNamespace(
        prompt_tokens=100, completion_tokens=20, cached_tokens=40
    )

    assert _usage_from_response(usage).cached_tokens == 40


def test_missing_cache_fields_default_to_zero():
    usage = SimpleNamespace(prompt_tokens=100, completion_tokens=20)
    assert _usage_from_response(usage).cached_tokens == 0
    assert _usage_from_response(None).cached_tokens == 0
