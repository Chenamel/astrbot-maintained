"""The model must be told which account is its own.

Without that line every participant has a name except the bot itself, and a
transcript of other people's words invites it to attribute one of them to
itself. The 2026-11-02 11:58 proactive reply did exactly that: it called a line
written by 大肥鱼 "my own receipt".

Both request paths are covered here because they are built by different code:
normal replies go through ``_append_system_reminders``, proactive wording goes
through ``generate_with_persona`` and never touches that function.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from astrbot.core import proactive_persona
from astrbot.core.astr_main_agent import _append_system_reminders
from astrbot.core.platform.message_type import MessageType
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.utils.self_identity import self_identity_note

SELF_ID = "123456789"


class _Event:
    """Minimal stand-in: only the attributes the code under test reads."""

    unified_msg_origin = "default:GroupMessage:999000111"

    def __init__(
        self,
        self_id: str = SELF_ID,
        message_type: MessageType = MessageType.GROUP_MESSAGE,
    ) -> None:
        self._self_id = self_id
        self._message_type = message_type
        self.message_obj = SimpleNamespace(
            sender=SimpleNamespace(user_id="987654321", nickname="测试用户"),
            group_id="999000111",
            group=SimpleNamespace(group_name="测试群"),
        )

    def get_self_id(self) -> str:
        return self._self_id

    def get_message_type(self) -> MessageType:
        return self._message_type

    def get_platform_name(self) -> str:
        return "aiocqhttp"


def test_group_note_names_the_account_and_the_ownership_rule() -> None:
    note = self_identity_note(_Event())

    assert f"Your account: {SELF_ID}" in note
    assert "BOT" in note and "机器人" in note
    assert "do not claim" in note


def test_private_note_omits_the_transcript_rule() -> None:
    note = self_identity_note(_Event(message_type=MessageType.FRIEND_MESSAGE))

    assert f"Your account: {SELF_ID}" in note
    assert "transcript" not in note


def test_no_self_id_means_no_claim() -> None:
    assert self_identity_note(_Event(self_id="")) == ""


def test_non_scalar_self_id_is_rejected() -> None:
    """Upstream tests hand in MagicMock events; a mock must not become an id."""
    from unittest.mock import MagicMock

    event = MagicMock()
    event.get_self_id.return_value = MagicMock()

    assert self_identity_note(event) == ""


def test_normal_request_carries_the_note() -> None:
    req = ProviderRequest()
    _append_system_reminders(
        _Event(),
        req,
        {
            "identifier": True,
            "group_name_display": False,
            "datetime_system_prompt": False,
        },
        None,
    )

    text = "\n".join(getattr(part, "text", "") for part in req.extra_user_content_parts)
    assert f"Your account: {SELF_ID}" in text
    # The upstream line stays untouched.
    assert "User ID: 987654321, Nickname: 测试用户" in text


def test_proactive_persona_request_carries_the_note(monkeypatch) -> None:
    captured: dict = {}

    class _FakeProvider:
        def get_model(self) -> str:
            return "fake-model"

        def meta(self) -> SimpleNamespace:
            return SimpleNamespace(id="fake-provider")

        async def text_chat(self, **kwargs):
            captured.update(kwargs)
            return LLMResponse(role="assistant", completion_text="好")

    async def fake_resolve(_context, _provider_id):
        return _FakeProvider()

    async def fake_hook(_event, _hook_type, _req):
        return False

    monkeypatch.setattr(proactive_persona, "_resolve_provider", fake_resolve)
    monkeypatch.setattr(proactive_persona, "call_event_hook", fake_hook)

    context = SimpleNamespace(persona_manager=None)
    response = asyncio.run(
        proactive_persona.generate_with_persona(context, _Event(), "说点什么")
    )

    assert response is not None
    assert f"Your account: {SELF_ID}" in captured["system_prompt"]
