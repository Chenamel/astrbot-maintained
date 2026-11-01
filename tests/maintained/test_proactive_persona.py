"""Persona-aware generation for plugin-driven proactive replies.

The point of this capability is that ``Context.llm_generate`` skips the
``on_llm_request`` hook, which is where persona and memory plugins do their
work. These tests pin down that the hook really runs and that whatever it
writes into the request actually reaches the provider.
"""

import asyncio
import types

import pytest

from astrbot.api import proactive as proactive_api
from astrbot.core import proactive_persona
from astrbot.core.pipeline.process_stage.method.agent_sub_stages import image_input


class _FakeProvider:
    """Records what it was called with and returns a canned response."""

    #: Read by the image helper to decide whether the provider can see pixels.
    provider_config = {"modalities": ["text", "image"]}

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def text_chat(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(completion_text="generated")


def _context(provider: _FakeProvider | None, by_id=None):
    return types.SimpleNamespace(
        provider_manager=types.SimpleNamespace(
            get_provider_by_id=by_id,
            curr_provider_inst=provider,
        )
    )


def _event():
    return types.SimpleNamespace(unified_msg_origin="default:GroupMessage:1")


def test_hook_rewrite_reaches_the_provider(monkeypatch):
    """A plugin writing persona into the request must be honoured."""
    provider = _FakeProvider()
    seen: dict = {}

    async def fake_hook(event, event_type, req):
        seen["event_type"] = event_type
        req.system_prompt = "人格：说话简短，带个人判断"
        return False

    monkeypatch.setattr(proactive_persona, "call_event_hook", fake_hook)

    resp = asyncio.run(
        proactive_persona.generate_with_persona(
            _context(provider), _event(), "群里有人问配置在哪"
        )
    )

    assert resp is not None
    assert seen["event_type"].name == "OnLLMRequestEvent"
    assert provider.calls[0]["system_prompt"] == "人格：说话简短，带个人判断"


def test_hook_cancelling_skips_the_provider(monkeypatch):
    """A plugin may veto the request; nothing should be sent."""
    provider = _FakeProvider()

    async def fake_hook(event, event_type, req):
        return True

    monkeypatch.setattr(proactive_persona, "call_event_hook", fake_hook)

    resp = asyncio.run(
        proactive_persona.generate_with_persona(_context(provider), _event(), "x")
    )

    assert resp is None
    assert provider.calls == []


def test_no_provider_returns_none():
    resp = asyncio.run(
        proactive_persona.generate_with_persona(_context(None), _event(), "x")
    )
    assert resp is None


def test_prompt_and_session_are_forwarded(monkeypatch):
    provider = _FakeProvider()

    async def fake_hook(event, event_type, req):
        return False

    async def fake_prepare(req, event, **kwargs):
        # The real one compresses and localises; this test is about what gets
        # forwarded, so it only needs to stand in for the rewrite.
        req.image_urls = ["/tmp/prepared.png"]

    monkeypatch.setattr(proactive_persona, "call_event_hook", fake_hook)
    monkeypatch.setattr(image_input, "prepare_request_images", fake_prepare)

    asyncio.run(
        proactive_persona.generate_with_persona(
            _context(provider), _event(), "说话", image_urls=["http://x/y.png"]
        )
    )

    assert provider.calls[0]["prompt"] == "说话"
    # Prepared reference, not the raw URL: the provider must receive whatever
    # the shared pipeline decided is sendable.
    assert provider.calls[0]["image_urls"] == ["/tmp/prepared.png"]


def test_api_degrades_to_none_when_core_patch_is_absent(monkeypatch):
    """Plugins must get a safe default instead of an ImportError."""
    monkeypatch.setattr(proactive_api, "resolve", lambda *a, **k: None)

    assert proactive_api.persona_available() is False
    assert (
        asyncio.run(
            proactive_api.generate_with_persona(
                _context(_FakeProvider()), _event(), "x"
            )
        )
        is None
    )


def test_api_reports_availability_when_installed():
    # The core module ships with this fork, so the capability is present.
    assert proactive_api.persona_available() is True


def test_public_surface_is_declared():
    assert "generate_with_persona" in proactive_api.__all__


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
