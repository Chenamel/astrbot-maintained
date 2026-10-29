"""A proactive reply must carry the configured persona.

The persona lives in core and is normally applied by the agent path from a
conversation context. A one-shot call has none, so before this it went out with
an empty system prompt: the 1.3k-character persona only ever reached @-mentions.

These tests drive the real function with stand-ins and assert on the request the
provider actually receives -- the only place the injection can be observed.
"""

import sys

import pytest

from astrbot.core import proactive_persona

pytestmark = pytest.mark.asyncio


class _Provider:
    """Captures the request instead of calling a model."""

    def __init__(self) -> None:
        self.seen = None

    def meta(self):
        class _Meta:
            id = "fake"

        return _Meta()

    async def text_chat(self, **kwargs):
        self.seen = kwargs

        class _Resp:
            role = "assistant"
            usage = None
            completion_text = "ok"

        return _Resp()

    def get_model(self):
        return "fake-model"


class _PersonaManager:
    def __init__(self, persona):
        self._persona = persona

    async def resolve_selected_persona(self, **kwargs):
        return ("默认", self._persona, None, False)


class _Context:
    def __init__(self, persona):
        self.persona_manager = _PersonaManager(persona)
        self.provider_manager = type("PM", (), {"curr_provider_inst": _Provider()})()


class _Event:
    unified_msg_origin = "default:GroupMessage:1"

    def get_platform_name(self):
        return "aiocqhttp"


async def _run(monkeypatch, persona):
    provider = _Provider()
    context = _Context(persona)
    context.provider_manager.curr_provider_inst = provider

    async def _no_hooks(event, event_type, req):
        return False

    monkeypatch.setattr(proactive_persona, "call_event_hook", _no_hooks)
    monkeypatch.setattr(
        proactive_persona,
        "db_helper",
        type("DB", (), {"insert_provider_stat": _noop}),
        raising=False,
    )

    await proactive_persona.generate_with_persona(context, _Event(), "说点什么")
    return provider.seen


async def _noop(**kwargs):
    return None


async def test_persona_prompt_reaches_the_request(monkeypatch):
    seen = await _run(monkeypatch, {"prompt": "你是群友，说话简短", "name": "默认"})

    assert seen is not None
    assert "# Persona Instructions" in seen["system_prompt"]
    assert "你是群友，说话简短" in seen["system_prompt"]


async def test_absent_persona_leaves_the_request_alone(monkeypatch):
    """No persona configured is not an error -- the call still proceeds."""
    seen = await _run(monkeypatch, None)

    assert seen is not None
    assert "# Persona Instructions" not in seen["system_prompt"]


async def test_begin_dialogs_are_prepended(monkeypatch):
    persona = {
        "prompt": "人设",
        "name": "默认",
        "_begin_dialogs_processed": [{"role": "user", "content": "在吗"}],
    }
    provider = _Provider()
    context = _Context(persona)
    context.provider_manager.curr_provider_inst = provider

    async def _no_hooks(event, event_type, req):
        return False

    monkeypatch.setattr(proactive_persona, "call_event_hook", _no_hooks)
    monkeypatch.setattr(
        proactive_persona,
        "db_helper",
        type("DB", (), {"insert_provider_stat": _noop}),
        raising=False,
    )

    await proactive_persona.generate_with_persona(context, _Event(), "说点什么")

    contexts = provider.seen.get("contexts") or []
    assert contexts and contexts[0]["content"] == "在吗"
