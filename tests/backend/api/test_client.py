"""`make_provider` / `llm_credentials`：按配置选择厂商与凭据。"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai4edu.api.client import llm_credentials, make_client, make_provider
from ai4edu.api.deepseek import DeepSeekProvider
from ai4edu.api.glm import GLMProvider
from ai4edu.config import Settings

GLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "data_dir": tmp_path / "data",
        "config_dir": tmp_path / "config",
    }
    values.update(overrides)
    return Settings(**values)


def test_make_provider_defaults_to_glm(tmp_path):
    """回归 #24：不读开发机上的 backend/.env，干净检出也能通过。"""

    settings = _settings(tmp_path, llm_api_key="test-key")

    provider = make_provider(settings)

    assert isinstance(provider, GLMProvider)
    assert provider.name == "glm"
    assert llm_credentials(settings) == (GLM_BASE_URL, "test-key")
    assert str(make_client(settings).base_url).rstrip("/") == GLM_BASE_URL


def test_make_provider_deepseek_uses_deepseek_key_and_default_base(tmp_path):
    settings = _settings(
        tmp_path,
        llm_provider="deepseek",
        deepseek_api_key="ds-key",
    )

    provider = make_provider(settings)

    assert isinstance(provider, DeepSeekProvider)
    assert provider.name == "deepseek"
    assert llm_credentials(settings) == (DEEPSEEK_BASE_URL, "ds-key")
    client = make_client(settings)
    assert str(client.base_url).rstrip("/") == DEEPSEEK_BASE_URL
    assert client.api_key == "ds-key"


def test_explicit_llm_api_key_wins_over_deepseek_key(tmp_path):
    settings = _settings(
        tmp_path,
        llm_provider="deepseek",
        llm_api_key="main-key",
        deepseek_api_key="ds-key",
    )

    assert llm_credentials(settings) == (DEEPSEEK_BASE_URL, "main-key")


def test_deepseek_base_url_used_for_chat_when_llm_base_url_empty(tmp_path):
    """LLM_BASE_URL 留空时，聊天与联网工具共用 DEEPSEEK_BASE_URL。"""

    settings = _settings(
        tmp_path,
        llm_provider="deepseek",
        deepseek_api_key="ds-key",
        deepseek_base_url="https://proxy.test",
    )

    assert llm_credentials(settings) == ("https://proxy.test", "ds-key")


def test_explicit_llm_base_url_overrides_default(tmp_path):
    settings = _settings(
        tmp_path,
        llm_provider="deepseek",
        llm_api_key="main-key",
        llm_base_url="https://proxy.test/v1",
    )

    assert llm_credentials(settings) == ("https://proxy.test/v1", "main-key")


def test_make_provider_rejects_unknown_vendor(tmp_path):
    settings = _settings(tmp_path, llm_provider="unknown")

    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        make_provider(settings)


def test_llm_credentials_rejects_unknown_vendor(tmp_path):
    settings = _settings(tmp_path, llm_provider="unknown")

    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        llm_credentials(settings)
