"""新对话里先上传图片、再创建会话时，图片要能在之后的回合中继续加载。"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai4edu.api.glm import GLMProvider
from ai4edu.config import Settings
from ai4edu.core.events import AgentError, TurnFinished
from ai4edu.core.query_engine import QueryEngine
from ai4edu.prompts import load_reminders
from ai4edu.storage.repos import attachments as attachments_repo
from ai4edu.tutoring.framework import load_config
from fakes import FakeLLMClient, FakeResponse

pytestmark = pytest.mark.asyncio

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"

# 最小的合法 PNG（1×1 像素）。
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


async def _upload_without_conversation(session_factory, settings, user_id: int) -> int:
    """模拟前端在新对话里上传：此时还没有会话，conversation_id 为空。"""

    path = settings.uploads_dir / str(user_id) / "photo.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_PNG)
    async with session_factory() as session:
        row = await attachments_repo.create(
            session,
            user_id=user_id,
            conversation_id=None,
            file_path=str(path.relative_to(settings.uploads_dir)),
            mime_type="image/png",
            size=len(_PNG),
            sha256="0" * 64,
        )
        await session.commit()
        return row.id


async def _turn(engine, user, conversation_id, text, attachment_ids):
    return [
        event
        async for event in engine.run_turn(
            user=user,
            conversation_id=conversation_id,
            text=text,
            attachment_ids=attachment_ids,
        )
    ]


async def test_image_uploaded_before_conversation_loads_on_later_turns(
    seed, session_factory, tmp_path
):
    """回归：错误记录 #16 —— 新对话先发照片，从第二条消息起每次都"出了点问题"。"""

    settings = Settings(data_dir=tmp_path / "data", config_dir=CONFIG_DIR)
    user, conversation_id = await seed()
    attachment_id = await _upload_without_conversation(
        session_factory, settings, user.id
    )

    # 两个回合都直接写正文回复，只关心历史里的图片能否加载。
    client = FakeLLMClient(
        [FakeResponse(text=["先看图。"]), FakeResponse(text=["不客气。"])]
    )
    engine = QueryEngine(
        settings=settings,
        config=load_config(CONFIG_DIR),
        reminders=load_reminders(CONFIG_DIR),
        provider=GLMProvider(client),
        session_factory=session_factory,
    )

    await _turn(engine, user, conversation_id, "这题怎么做", [attachment_id])
    second = await _turn(engine, user, conversation_id, "谢谢", [])

    assert not [e for e in second if isinstance(e, AgentError)]
    # 第二回合的请求里仍然带着第一回合的图片。
    second_request = client.messages(-1)
    image_parts = [
        part
        for message in second_request
        if isinstance(message.get("content"), list)
        for part in message["content"]
        if part.get("type") == "image_url"
    ]
    assert len(image_parts) == 1
    assert image_parts[0]["image_url"]["url"].startswith("data:image/png;base64,")

    async with session_factory() as session:
        row = await attachments_repo.get(session, attachment_id, user.id)
    assert row.conversation_id == conversation_id


async def test_link_does_not_steal_attachment_from_other_conversation(
    seed, session_factory
):
    """已归属其他会话的附件不会被挂到当前会话上。"""

    user, first_conversation = await seed()
    _, second_conversation = await seed()
    async with session_factory() as session:
        row = await attachments_repo.create(
            session,
            user_id=user.id,
            conversation_id=first_conversation,
            file_path="x.png",
            mime_type="image/png",
            size=1,
            sha256="0" * 64,
        )
        await session.commit()
        await attachments_repo.link_to_conversation(
            session, [row.id], second_conversation, user.id
        )
        await session.commit()
        reloaded = await attachments_repo.get(session, row.id, user.id)
    assert reloaded.conversation_id == first_conversation
