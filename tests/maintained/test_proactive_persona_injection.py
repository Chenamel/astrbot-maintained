"""A proactive reply must carry the configured persona.

The persona lives in core and is normally applied by the agent path from a
conversation context. A one-shot call has no such context, so the system prompt
must be assembled explicitly or the persona never reaches it.

These tests drive the real function with stand-ins and assert on the request the
provider actually receives -- the only place the injection can be observed.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import astrbot.api  # noqa: F401 - initialize the existing API import cycle first
from astrbot.core import db_helper, persona_mgr, proactive_persona
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.provider import manager as provider_manager_module
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.provider.provider import Provider
from astrbot.core.star.context import Context

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def isolate_provider_stats(monkeypatch):
    # The implementation imports this object inside finally, not from its module.
    monkeypatch.setattr(db_helper, "insert_provider_stat", AsyncMock())


@pytest.fixture
def session_generation(monkeypatch):
    """Real selection managers; only persistence, hooks and model I/O are faked."""
    umo = "default:GroupMessage:1"
    configs = {}
    preferences = {}
    rules = {}
    default_config = {
        "agent_runner": {
            "runner_type": "local",
            "config": {
                "model": {"provider_id": "configured"},
                "persona": {"persona_id": "default"},
            },
        }
    }
    acm = SimpleNamespace(
        default_conf=default_config,
        get_conf=lambda origin: configs.get(origin, default_config),
    )

    async def get_preference(scope, scope_id, key, default=None):
        assert scope == "umo"
        if key == "session_service_config":
            return rules.get(scope_id, default)
        assert key == "provider_perf_chat_completion"
        return preferences.get(scope_id, default)

    monkeypatch.setattr(provider_manager_module.sp, "get_async", get_preference)
    monkeypatch.setattr(
        provider_manager_module.sp, "session_get", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        proactive_persona, "call_event_hook", AsyncMock(return_value=False)
    )
    providers = {}
    for provider_id in ("global", "configured", "selected", "override"):
        provider = MagicMock(spec=Provider)
        provider.meta.return_value = SimpleNamespace(id=provider_id)
        provider.get_model.return_value = provider_id
        provider.text_chat = AsyncMock(
            return_value=LLMResponse(role="assistant", completion_text=provider_id)
        )
        providers[provider_id] = provider
    manager = object.__new__(ProviderManager)
    manager.acm = acm
    manager.inst_map = providers
    manager.provider_insts = list(providers.values())
    manager.curr_provider_inst = providers["global"]
    personas = persona_mgr.PersonaManager(MagicMock(), acm)
    personas.personas_v3 = [
        {"name": name, "prompt": f"PERSONA_{name}", "_begin_dialogs_processed": []}
        for name in ("default", "selected", "forced")
    ]
    db = SimpleNamespace(get_conversation_by_id=AsyncMock(return_value=None))
    conversations = ConversationManager(db)
    context = SimpleNamespace(
        provider_manager=manager,
        persona_manager=personas,
        conversation_manager=conversations,
    )
    context.get_using_provider_async = Context.get_using_provider_async.__get__(context)

    def select_persona(persona_id):
        conversations.session_conversations[umo] = "conversation-1"
        db.get_conversation_by_id.return_value = SimpleNamespace(
            platform_id="default",
            user_id=umo,
            conversation_id="conversation-1",
            content=[],
            title="test",
            persona_id=persona_id,
            created_at=None,
            updated_at=None,
            token_usage=0,
        )

    async def generate(**kwargs):
        return await proactive_persona.generate_with_persona(
            context, _Event(), "say", **kwargs
        )

    return SimpleNamespace(
        umo=umo,
        context=context,
        providers=providers,
        preferences=preferences,
        configs=configs,
        rules=rules,
        db=db,
        conversations=conversations,
        select_persona=select_persona,
        generate=generate,
    )


@pytest.mark.parametrize("preference", ["selected", None, "deleted"])
async def test_generation_uses_session_model_selection(session_generation, preference):
    case = session_generation
    case.preferences[case.umo] = preference
    expected = "selected" if preference == "selected" else "configured"
    response = await case.generate()
    assert response.completion_text == expected
    case.providers["global"].text_chat.assert_not_awaited()


@pytest.mark.parametrize("provider_id", ["override", "missing"])
async def test_explicit_model_never_falls_back_to_session(
    session_generation, provider_id
):
    case = session_generation
    case.preferences[case.umo] = "selected"
    response = await case.generate(chat_provider_id=provider_id)
    if provider_id == "missing":
        assert response is None
    else:
        assert response.completion_text == provider_id
    case.providers["selected"].text_chat.assert_not_awaited()


@pytest.mark.parametrize("persona_id", ["selected", "[%None]", None])
async def test_generation_uses_selected_conversation_persona(
    session_generation, persona_id
):
    case = session_generation
    case.select_persona(persona_id)
    await case.generate(chat_provider_id="override")
    prompt = case.providers["override"].text_chat.call_args.kwargs["system_prompt"]
    if persona_id == "[%None]":
        assert "# Persona Instructions" not in prompt
    else:
        assert f"PERSONA_{persona_id or 'default'}" in prompt
    case.db.get_conversation_by_id.assert_awaited_once_with(cid="conversation-1")


async def test_session_rule_still_overrides_conversation_persona(session_generation):
    case = session_generation
    case.select_persona("selected")
    case.rules[case.umo] = {"persona_id": "forced"}
    await case.generate(chat_provider_id="override")
    prompt = case.providers["override"].text_chat.call_args.kwargs["system_prompt"]
    assert "PERSONA_forced" in prompt
    assert "PERSONA_selected" not in prompt


@pytest.mark.parametrize("stale_selection", [False, True])
async def test_absent_conversation_uses_default_without_creating(
    session_generation, stale_selection
):
    case = session_generation
    if stale_selection:
        case.conversations.session_conversations[case.umo] = "deleted"
    await case.generate(chat_provider_id="override")
    prompt = case.providers["override"].text_chat.call_args.kwargs["system_prompt"]
    assert "PERSONA_default" in prompt
    assert case.conversations.session_conversations == (
        {case.umo: "deleted"} if stale_selection else {}
    )
    assert case.db.get_conversation_by_id.await_count == int(stale_selection)


async def test_session_selection_is_not_cached_across_calls(session_generation):
    case = session_generation
    case.preferences[case.umo] = "selected"
    assert (await case.generate()).completion_text == "selected"
    case.preferences[case.umo] = "override"
    assert (await case.generate()).completion_text == "override"
    case.select_persona("selected")
    await case.generate(chat_provider_id="override")
    case.select_persona("[%None]")
    await case.generate(chat_provider_id="override")
    prompt = case.providers["override"].text_chat.call_args.kwargs["system_prompt"]
    assert "# Persona Instructions" not in prompt


async def test_session_provider_none_does_not_use_global_fallback(session_generation):
    case = session_generation
    case.context.get_using_provider_async = AsyncMock(return_value=None)
    assert await case.generate() is None
    case.providers["global"].text_chat.assert_not_awaited()


async def test_session_provider_error_does_not_use_global_fallback(session_generation):
    case = session_generation
    case.context.get_using_provider_async = AsyncMock(
        side_effect=ValueError("invalid type")
    )
    with pytest.raises(ValueError, match="invalid type"):
        await case.generate()
    for provider in case.providers.values():
        provider.text_chat.assert_not_awaited()


async def test_no_available_provider_returns_none(session_generation):
    case = session_generation
    case.context.provider_manager.inst_map = {}
    case.context.provider_manager.provider_insts = []
    assert await case.generate() is None
    case.providers["global"].text_chat.assert_not_awaited()


@pytest.mark.parametrize("lookup", ["get_curr_conversation_id", "get_conversation"])
async def test_conversation_read_failure_keeps_existing_skip_behavior(
    session_generation, monkeypatch, lookup
):
    case = session_generation
    case.select_persona("selected")
    warnings = []
    monkeypatch.setattr(
        proactive_persona.logger, "warning", lambda *args: warnings.append(args)
    )
    setattr(
        case.conversations, lookup, AsyncMock(side_effect=RuntimeError("unavailable"))
    )
    await case.generate(chat_provider_id="override")
    prompt = case.providers["override"].text_chat.call_args.kwargs["system_prompt"]
    assert "# Persona Instructions" not in prompt
    assert any("proactive persona injection skipped" in args[0] for args in warnings)


@pytest.mark.parametrize("persona_id", [None, "selected", "[%None]"])
async def test_webchat_persona_selection_keeps_resolver_semantics(
    session_generation, persona_id
):
    case = session_generation
    case.select_persona(persona_id)
    event = SimpleNamespace(
        unified_msg_origin=case.umo, get_platform_name=lambda: "webchat"
    )
    await proactive_persona.generate_with_persona(
        case.context, event, "say", chat_provider_id="override"
    )
    prompt = case.providers["override"].text_chat.call_args.kwargs["system_prompt"]
    if persona_id == "selected":
        assert "PERSONA_selected" in prompt
    else:
        assert "# Persona Instructions" not in prompt


async def test_selected_persona_begin_dialogs_are_copied_without_history(
    session_generation,
):
    case = session_generation
    case.select_persona("selected")
    dialogs = [{"role": "user", "content": "selected opening"}]
    case.context.persona_manager.personas_v3[1]["_begin_dialogs_processed"] = dialogs
    case.db.get_conversation_by_id.return_value.content = [
        {"role": "user", "content": "not imported"}
    ]
    await case.generate(chat_provider_id="override")
    forwarded = case.providers["override"].text_chat.call_args.kwargs["contexts"]
    assert forwarded == dialogs
    forwarded[0]["content"] = "changed"
    assert dialogs[0]["content"] == "selected opening"


async def test_provider_timeout_still_applies_after_selection(session_generation):
    import asyncio

    case = session_generation
    case.preferences[case.umo] = "selected"

    async def wait_for_cancellation(**kwargs):
        await asyncio.Event().wait()

    case.providers["selected"].text_chat.side_effect = wait_for_cancellation
    with pytest.raises(TimeoutError):
        await case.generate(timeout=0.01)
    case.providers["global"].text_chat.assert_not_awaited()


async def test_different_origins_keep_model_and_persona_isolated(session_generation):
    case = session_generation
    case.select_persona("selected")
    other_umo = "other:GroupMessage:2"
    case.configs[other_umo] = {
        "agent_runner": {
            "runner_type": "local",
            "config": {
                "model": {"provider_id": "override"},
                "persona": {"persona_id": "forced"},
            },
        }
    }
    case.preferences[case.umo] = "selected"
    first = await case.generate()
    other_event = SimpleNamespace(
        unified_msg_origin=other_umo, get_platform_name=lambda: "aiocqhttp"
    )
    second = await proactive_persona.generate_with_persona(
        case.context, other_event, "say"
    )
    assert first.completion_text == "selected"
    assert second.completion_text == "override"
    assert (
        "PERSONA_selected"
        in case.providers["selected"].text_chat.call_args.kwargs["system_prompt"]
    )
    assert (
        "PERSONA_forced"
        in case.providers["override"].text_chat.call_args.kwargs["system_prompt"]
    )
    case.db.get_conversation_by_id.assert_awaited_once_with(cid="conversation-1")


async def test_public_api_keeps_session_selection(session_generation):
    from astrbot.api import proactive

    case = session_generation
    case.preferences[case.umo] = "selected"
    case.select_persona("selected")
    response = await proactive.generate_with_persona(case.context, _Event(), "say")
    assert response.completion_text == "selected"
    assert (
        "PERSONA_selected"
        in case.providers["selected"].text_chat.call_args.kwargs["system_prompt"]
    )


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


async def _run(monkeypatch, persona, hook=None):
    provider = _Provider()
    context = _Context(persona)
    context.provider_manager.curr_provider_inst = provider

    async def _no_hooks(event, event_type, req):
        return False

    monkeypatch.setattr(proactive_persona, "call_event_hook", hook or _no_hooks)
    monkeypatch.setattr(
        db_helper,
        "insert_provider_stat",
        _noop,
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
        db_helper,
        "insert_provider_stat",
        _noop,
    )

    await proactive_persona.generate_with_persona(context, _Event(), "说点什么")

    contexts = provider.seen.get("contexts") or []
    assert contexts and contexts[0]["content"] == "在吗"


async def test_hook_injected_parts_reach_the_provider(monkeypatch):
    """Memory recalls and role notes appended by hooks must survive.

    ``generate_with_persona`` runs the ``on_llm_request`` hooks on its own
    request; calling the provider without ``extra_user_content_parts`` would
    discard every part a hook added --
    long-term memory, the role note, the at-all permission block -- while the
    docstring promised they would contribute exactly as in a normal reply.
    """
    from astrbot.core.agent.message import TextPart

    async def _hook(event, event_type, req):
        req.extra_user_content_parts.append(
            TextPart(text="<system_reminder>Role: member</system_reminder>")
        )
        return False

    seen = await _run(monkeypatch, {"prompt": "人设", "name": "默认"}, hook=_hook)

    parts = seen.get("extra_user_content_parts") or []
    texts = [getattr(part, "text", "") for part in parts]
    assert any("Role: member" in text for text in texts)
