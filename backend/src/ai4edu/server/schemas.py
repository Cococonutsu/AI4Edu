"""HTTP 请求/响应模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _ensure_utc(value: object) -> object:
    """SQLite 读回的时间不带时区，输出时统一标记为 UTC。"""
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator("created_at", "updated_at", mode="before", check_fields=False)
    @classmethod
    def _utc_datetime(cls, value: object) -> object:
        return _ensure_utc(value)


class UserOut(ORMModel):
    id: int
    username: str
    display_name: str
    grade_band: str
    grade: int
    role: str
    is_active: bool
    created_at: datetime


class LoginRequest(BaseModel):
    username: str
    password: str


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("标题不能为空")
        return value


class ConversationOut(ORMModel):
    id: int
    title: str
    phase: str
    # 这个对话是否正在后台生成回复（学生切走后仍在继续）。
    running: bool = False
    created_at: datetime
    updated_at: datetime


class VisibleAttachment(BaseModel):
    id: int
    url: str


class VisibleMessage(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    text: str
    attachments: list[VisibleAttachment] = Field(default_factory=list)
    # 该回合里 `draw_figure` 打开过的图（结构化描述，前端直接渲染）。
    figures: list[dict] = Field(default_factory=list)
    created_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[VisibleMessage] = Field(default_factory=list)


class AttachmentOut(ORMModel):
    id: int
    url: str
    mime_type: str
    size: int
    created_at: datetime


class MessageCreate(BaseModel):
    """发送消息的请求体（路由目前返回 501，模型先定义好）。"""

    text: str = Field(default="", max_length=20000)
    attachment_ids: list[int] = Field(default_factory=list)
