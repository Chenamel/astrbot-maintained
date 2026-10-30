"""Our own replies must land in the same history we read.

Without the record, later turns see the group's lines but not the bot's, so it
repeats itself and cannot notice it has already said something. The write also
has to use the same conversation key the reader computes, or the row lands in
one conversation and is looked up in another.
"""

import pytest

from astrbot.api import proactive

pytestmark = pytest.mark.asyncio


class _Event:
    unified_msg_origin = "default:GroupMessage:1039252505"

    def get_platform_id(self):
        return "default"


class _DbStub:
    def __init__(self):
        self.calls = []

    async def insert_platform_message_history(self, **kwargs):
        self.calls.append(kwargs)


async def test_reply_is_written_with_the_bot_marker(monkeypatch):
    stub = _DbStub()
    monkeypatch.setattr("astrbot.core.db_helper", stub, raising=False)

    ok = await proactive.record_bot_message(None, _Event(), "黄圈C是配队卡片的标记")

    assert ok is True
    row = stub.calls[0]
    assert row["sender_id"] == "bot"
    assert row["sender_name"] == "bot"
    assert row["content"]["type"] == "bot"
    assert row["content"]["message"][0]["text"] == "黄圈C是配队卡片的标记"


async def test_the_conversation_key_matches_the_reader(monkeypatch):
    """Written under platform_id:session, which is what _history looks up."""
    stub = _DbStub()
    monkeypatch.setattr("astrbot.core.db_helper", stub, raising=False)

    await proactive.record_bot_message(None, _Event(), "一句话")

    assert stub.calls[0]["user_id"] == "default:GroupMessage:1039252505"


async def test_empty_text_is_not_recorded(monkeypatch):
    stub = _DbStub()
    monkeypatch.setattr("astrbot.core.db_helper", stub, raising=False)

    assert await proactive.record_bot_message(None, _Event(), "") is False
    assert stub.calls == []


async def test_a_failed_write_is_not_fatal(monkeypatch):
    class _Boom:
        async def insert_platform_message_history(self, **kwargs):
            raise RuntimeError("db is down")

    monkeypatch.setattr("astrbot.core.db_helper", _Boom(), raising=False)

    assert await proactive.record_bot_message(None, _Event(), "一句话") is False


class _UserEvent:
    """Carries the sender fields a user message has."""

    unified_msg_origin = "default:GroupMessage:1039252505"

    def get_platform_id(self):
        return "default"

    def get_sender_id(self):
        return "3231558257"

    def get_sender_name(self):
        return "镜花水月"


async def test_user_message_records_sender(monkeypatch):
    stub = _DbStub()
    monkeypatch.setattr("astrbot.core.db_helper", stub, raising=False)

    ok = await proactive.record_user_message(
        None, _UserEvent(), "公司这玩意儿不像存护体系的"
    )

    assert ok is True
    row = stub.calls[0]
    assert row["sender_id"] == "3231558257"
    assert row["sender_name"] == "镜花水月"
    assert row["content"]["type"] == "user"
    assert row["user_id"] == "default:GroupMessage:1039252505"


async def test_empty_user_text_is_skipped(monkeypatch):
    stub = _DbStub()
    monkeypatch.setattr("astrbot.core.db_helper", stub, raising=False)

    assert await proactive.record_user_message(None, _UserEvent(), "") is False
    assert stub.calls == []
