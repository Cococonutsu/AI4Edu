"""`make_provider`：按配置选择厂商。"""

from __future__ import annotations

import pytest

from ai4edu.api.client import make_provider
from ai4edu.api.glm import GLMProvider
from ai4edu.config import Settings


def test_make_provider_defaults_to_glm(tmp_path):
    """回归 #24：不读开发机上的 backend/.env，干净检出也能通过。"""

    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        llm_api_key="test-key",
    )

    provider = make_provider(settings)

    assert isinstance(provider, GLMProvider)
    assert provider.name == "glm"


def test_make_provider_rejects_unknown_vendor(tmp_path):
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        llm_provider="unknown",
    )

    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        make_provider(settings)
