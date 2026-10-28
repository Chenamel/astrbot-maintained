"""llm_generate() usage must reach the dashboard.

Context.llm_generate() persisted its stats by reading ``llm_resp.stats``, but
LLMResponse has no such attribute -- it carries a TokenUsage on ``.usage``. Every
call raised inside the try block, so the whole direct-LLM path was dropped from
provider_stats (662 warnings in a single day) and never showed up in the totals.
"""

from types import SimpleNamespace

import pytest

import astrbot.core.star.context as context_module
from astrbot.core.provider.entities import LLMResponse, TokenUsage
from astrbot.core.star.context import Context


class _FakeDB:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def insert_provider_stat(self, **kwargs) -> None:
        self.calls.append(kwargs)


class _FakeProvider(SimpleNamespace):
    async def text_chat(self, **kwargs):
        return self.response

    def get_model(self) -> str:
        return "fake-model"


def _response(usage=None, role="assistant") -> LLMResponse:
    resp = LLMResponse(role=role, completion_text="ok")
    resp.usage = usage
    return resp


def _context(monkeypatch, response) -> tuple[Context, _FakeDB]:
    monkeypatch.setattr(context_module, "Provider", SimpleNamespace)
    db = _FakeDB()
    monkeypatch.setattr("astrbot.core.db_helper", db)
    provider = _FakeProvider(response=response)
    ctx = Context(
        event_queue=SimpleNamespace(),
        config=SimpleNamespace(),
        db=SimpleNamespace(),
        provider_manager=SimpleNamespace(
            get_provider_by_id=lambda pid: _await(provider),
        ),
        platform_manager=SimpleNamespace(),
        conversation_manager=SimpleNamespace(),
        message_history_manager=SimpleNamespace(),
        persona_manager=SimpleNamespace(),
        astrbot_config_mgr=SimpleNamespace(),
        knowledge_base_manager=SimpleNamespace(),
        cron_manager=SimpleNamespace(),
    )
    return ctx, db


def _await(value):
    async def _coro():
        return value

    return _coro()


@pytest.mark.asyncio
async def test_usage_is_persisted(monkeypatch):
    ctx, db = _context(monkeypatch, _response(TokenUsage(11, 7, 5)))
    await ctx.llm_generate(umo="umo", chat_provider_id="p", prompt="hi")
    assert len(db.calls) == 1
    call = db.calls[0]
    assert call["stats"]["token_usage"] == {
        "input_other": 11,
        "input_cached": 7,
        "output": 5,
    }
    assert call["agent_type"] == "llm_generate"
    assert call["status"] == "completed"


@pytest.mark.asyncio
async def test_missing_usage_still_records_timing(monkeypatch):
    """A response without usage has no tokens, but the call still took time.

    The call log used to show "-" for duration on every plugin-driven call
    because only token usage was persisted.
    """
    ctx, db = _context(monkeypatch, _response(usage=None))
    await ctx.llm_generate(umo="umo", chat_provider_id="p", prompt="hi")
    stats = db.calls[0]["stats"]
    assert "token_usage" not in stats
    assert 0 < stats["start_time"] <= stats["end_time"]


@pytest.mark.asyncio
async def test_timing_is_recorded_alongside_usage(monkeypatch):
    ctx, db = _context(monkeypatch, _response(TokenUsage(11, 7, 5)))
    await ctx.llm_generate(umo="umo", chat_provider_id="p", prompt="hi")
    stats = db.calls[0]["stats"]
    assert stats["token_usage"] == {"input_other": 11, "input_cached": 7, "output": 5}
    assert 0 < stats["start_time"] <= stats["end_time"]


@pytest.mark.asyncio
async def test_error_response_is_recorded_as_error(monkeypatch):
    ctx, db = _context(monkeypatch, _response(TokenUsage(1, 0, 0), role="err"))
    await ctx.llm_generate(umo="umo", chat_provider_id="p", prompt="hi")
    assert db.calls[0]["status"] == "error"


@pytest.mark.asyncio
async def test_no_umo_skips_persistence(monkeypatch):
    ctx, db = _context(monkeypatch, _response(TokenUsage(1, 0, 0)))
    await ctx.llm_generate(chat_provider_id="p", prompt="hi")
    assert db.calls == []
