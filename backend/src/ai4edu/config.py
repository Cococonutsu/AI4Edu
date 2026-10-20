"""应用配置。

环境变量来自 `backend/.env`（见 `.env.example`），未设置时使用默认值。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py 位于 backend/src/ai4edu/config.py：
# parents[0] = ai4edu, parents[1] = src, parents[2] = backend, parents[3] = 仓库根。
BACKEND_DIR = Path(__file__).resolve().parents[2]


def _is_repo_root(path: Path) -> bool:
    return (path / "config" / "framework").is_dir() and (path / "backend").is_dir()


def _find_repo_root() -> Path:
    """定位仓库根目录（同时包含 config/framework/ 与 backend/）。

    优先使用源码树中的固定层级；若安装方式导致路径不同，则逐级向上查找。
    """
    fixed = Path(__file__).resolve().parents[3]
    if _is_repo_root(fixed):
        return fixed
    for parent in Path(__file__).resolve().parents:
        if _is_repo_root(parent):
            return parent
    return fixed


REPO_ROOT = _find_repo_root()


class Settings(BaseSettings):
    """进程级配置。密钥只从环境或 `backend/.env` 读取。"""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    llm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    llm_api_key: str = ""
    # 模型厂商：api/client.make_provider 按此选择 Provider。
    llm_provider: str = "glm"
    llm_model_tutor: str = "glm-5.3-flash"

    data_dir: Path = REPO_ROOT / "data"
    config_dir: Path = REPO_ROOT / "config"

    session_ttl_hours: int = 168
    cookie_secure: bool = False

    @field_validator("data_dir", "config_dir", mode="after")
    @classmethod
    def _resolve_relative_path(cls, value: Path) -> Path:
        """相对路径按 backend/ 解析，绝对路径原样规范化。"""
        if not value.is_absolute():
            value = BACKEND_DIR / value
        return value.expanduser().resolve()

    @property
    def db_path(self) -> Path:
        return self.data_dir / "ai4edu.sqlite3"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
