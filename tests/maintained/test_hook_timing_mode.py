"""Hook timing modes of the tool-loop agent runner.

The fork fires the agent-completion hook **before** the reply is emitted
(``enhanced``); ``legacy`` restores the upstream ordering ("reply first,
completion hook after") on the skills-like re-query fallback path, which is the
only path where this fork actually diverges from upstream.

This file is self-contained: the fixtures in ``tests/test_tool_loop_agent_runner.py``
are module-local and cannot be shared, so the mocks are redefined here.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.astr_agent_run_util import run_agent
from astrbot.core.provider.entities import LLMResponse, ProviderRequest, TokenUsage
from astrbot.core.provider.provider import Provider

FINAL_TEXT = "The search is complete: two pushes."


class MockProvider(Provider):
    """Provider stub; subclasses override ``text_chat`` for a scripted dialogue."""

    def __init__(self) -> None:
        super().__init__({}, {})
        self.call_count = 0

    def get_current_key(self) -> str:
        return "test_key"

    def set_key(self, key: str) -> None:
        return None

    async def get_models(self) -> list[str]:
        return ["test_model"]

    async def text_chat(self, **kwargs) -> LLMResponse:
        self.call_count += 1
        return LLMResponse(
            role="assistant",
            completion_text="fallback reply",
            usage=TokenUsage(input_other=1, output=1),
        )

    async def text_chat_stream(self, **kwargs):
        response = await self.text_chat(**kwargs)
        response.is_chunk = True
        yield response
        response.is_chunk = False
        yield response


class RequeryReplyProvider(MockProvider):
    """Return a tool call first, then a plain reply with no tool call."""

    async def text_chat(self, **kwargs) -> LLMResponse:
        self.call_count += 1
        if self.call_count == 1:
            return LLMResponse(
                role="assistant",
                completion_text="Let me check.",
                tools_call_name=["test_tool"],
                tools_call_args=[{}],
                tools_call_ids=["select_tool"],
            )
        return LLMResponse(role="assistant", completion_text=FINAL_TEXT)


class MockToolExecutor:
    """Executor stub; the re-query fallback path must never invoke it."""

    @classmethod
    def execute(cls, tool, run_context, **tool_args):
        raise AssertionError("the re-query fallback path must not execute tools")


class MockHooks(BaseAgentRunHooks):
    """Record which agent hooks fired."""

    def __init__(self) -> None:
        self.agent_begin_called = False
        self.agent_done_called = False
        self.tool_start_called = False
        self.tool_end_called = False

    async def on_agent_begin(self, run_context) -> None:
        self.agent_begin_called = True

    async def on_tool_start(self, run_context, tool, tool_args) -> None:
        self.tool_start_called = True

    async def on_tool_end(self, run_context, tool, tool_args, tool_result) -> None:
        self.tool_end_called = True

    async def on_agent_done(self, run_context, llm_response) -> None:
        self.agent_done_called = True


class MockAgentContext:
    """Minimal agent context carrying the event."""

    def __init__(self, event) -> None:
        self.event = event


def _build_request() -> ProviderRequest:
    tool = FunctionTool(
        name="test_tool",
        description="test tool",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        handler=AsyncMock(),
    )
    return ProviderRequest(
        prompt="please look this up",
        func_tool=ToolSet(tools=[tool]),
        contexts=[],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("hook_timing_mode", "expected_hook_at_emission"),
    [("legacy", False), ("enhanced", True)],
)
async def test_skills_like_requery_hook_timing(
    hook_timing_mode: str,
    expected_hook_at_emission: bool,
):
    """The completion hook fires after the reply only in legacy mode.

    Args:
        hook_timing_mode: Mode passed to ``runner.reset``.
        expected_hook_at_emission: Whether ``on_agent_done`` has already run at
            the moment the final reply is yielded.
    """
    provider = RequeryReplyProvider()
    hooks = MockHooks()
    runner = ToolLoopAgentRunner()
    event = MagicMock()
    event.is_stopped.return_value = False
    event.get_extra.return_value = None
    event.get_platform_name.return_value = "lark"

    await runner.reset(
        provider=provider,
        request=_build_request(),
        run_context=ContextWrapper(context=MockAgentContext(event)),
        tool_executor=MockToolExecutor(),
        agent_hooks=hooks,
        streaming=False,
        tool_schema_mode="skills_like",
        hook_timing_mode=hook_timing_mode,
    )

    original_step = runner.step
    hooks_at_emission: list[bool] = []

    async def recorded_step():
        async for response in original_step():
            chain = response.data["chain"]
            if response.type == "llm_result" and chain.get_plain_text() == FINAL_TEXT:
                hooks_at_emission.append(hooks.agent_done_called)
            yield response

    runner.step = recorded_step
    chains = [chain async for chain in run_agent(runner)]

    # Legacy defers the hook until after the reply (upstream ordering);
    # enhanced fires it before, so audit plugins get control first.
    assert hooks_at_emission == [expected_hook_at_emission]
    # Either way the hook must still run exactly once before the runner is done.
    assert hooks.agent_done_called
    assert runner.done()
    assert runner.get_final_llm_resp().completion_text == FINAL_TEXT
    assert provider.call_count == 2
    assert sum(chain.get_plain_text() == FINAL_TEXT for chain in chains) == 1
    assert sum(chain.get_plain_text() == "Let me check." for chain in chains) == 1
    # The fallback path re-queries for tool arguments and never runs a tool.
    assert not hooks.tool_start_called


# --------------------------------------------------------------------------
# The mode belongs to a turn, not to the process
# --------------------------------------------------------------------------


def test_an_event_snapshot_wins_over_the_global():
    """Two bots with different profiles share one process.

    The global records "whoever built last", so without the event a plugin
    auditing bot B's reply could be told bot A's timing.
    """
    from types import SimpleNamespace

    from astrbot.core.config.agent_runner import (
        HOOK_TIMING_EXTRA,
        hook_timing_mode,
        set_hook_timing_mode,
    )

    store = {}
    event = SimpleNamespace(
        get_extra=lambda key, default=None: store.get(key, default),
        set_extra=lambda key, value: store.__setitem__(key, value),
    )

    set_hook_timing_mode("legacy", event)
    set_hook_timing_mode("enhanced")  # another bot builds afterwards

    assert hook_timing_mode(event) == "legacy", "the snapshot must win"
    assert hook_timing_mode() == "enhanced", "no event falls back to the last build"
    assert event.get_extra(HOOK_TIMING_EXTRA) == "legacy"


def test_a_plain_event_without_extras_is_tolerated():
    from types import SimpleNamespace

    from astrbot.core.config.agent_runner import hook_timing_mode, set_hook_timing_mode

    set_hook_timing_mode("enhanced", SimpleNamespace())
    set_hook_timing_mode("legacy")

    assert hook_timing_mode(SimpleNamespace()) == "legacy"


def test_the_public_api_accepts_an_event():
    from types import SimpleNamespace

    from astrbot.api.runtime import hook_timing_mode
    from astrbot.core.config.agent_runner import set_hook_timing_mode

    store = {}
    event = SimpleNamespace(
        get_extra=lambda key, default=None: store.get(key, default),
        set_extra=lambda key, value: store.__setitem__(key, value),
    )

    set_hook_timing_mode("enhanced", event)
    set_hook_timing_mode("legacy")

    assert hook_timing_mode(event) == "enhanced"
    assert hook_timing_mode() == "legacy"
