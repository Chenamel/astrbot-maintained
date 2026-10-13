"""The T8-12 Step 4a split of the tool-loop agent runner.

The three oversized-tool-result helpers moved into ``tool_loop_support``
(#37); the runner keeps thin delegating methods so the upstream test that
patches ``runner._write_tool_result_overflow_file`` on the *instance* keeps
working. Group A pins that contract (including delegate signature parity),
group B pins the behaviour of the moved helpers, which had no direct coverage.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace
from types import SimpleNamespace

import pytest

from astrbot.core.agent.runners import tool_loop_support
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = (
    REPO_ROOT / "astrbot" / "core" / "agent" / "runners" / "tool_loop_agent_runner.py"
)

#: Runner method -> support function.
DELEGATES = (
    ("_read_tool_hint", "read_tool_hint"),
    ("_write_tool_result_overflow_file", "write_tool_result_overflow_file"),
    ("_truncate_tool_result_preview", "truncate_tool_result_preview"),
    ("_track_tool_call_streak", "track_tool_call_streak"),
    ("_build_repeated_tool_call_guidance", "build_repeated_tool_call_guidance"),
    ("_iter_tool_executor_results", "iter_tool_executor_results"),
)

SUPPORT_ALL = (
    "build_repeated_tool_call_guidance",
    "iter_tool_executor_results",
    "read_tool_hint",
    "track_tool_call_streak",
    "truncate_tool_result_preview",
    "write_tool_result_overflow_file",
)

INTERNAL_SYMBOLS = ("_ToolExecutionInterrupted", "ToolExecutorResultT")


class _Counter:
    """Token counter stub: one token per four characters."""

    def count_tokens(self, messages) -> int:
        return len(messages[0].content) // 4


class _RunnerStub:
    """Runner stand-in exposing only what the support helpers read."""

    def __init__(
        self,
        *,
        overflow_dir: str | None = None,
        read_tool=None,
        preview_limit: int = 7000,
    ):
        self.tool_result_overflow_dir = overflow_dir
        self.read_tool = read_tool
        self.TOOL_RESULT_PREVIEW_MAX_ESTIMATED_TOKENS = preview_limit
        self._tool_result_token_counter = _Counter()


class _ReadTool:
    name = "astrbot_file_read_tool"


def test_support_module_declares_its_public_surface():
    """#37 lists exactly the helpers it owns, and nothing internal."""
    assert tool_loop_support.__all__ == list(SUPPORT_ALL)
    for name in SUPPORT_ALL:
        assert callable(getattr(tool_loop_support, name)), name
    for name in INTERNAL_SYMBOLS:
        assert hasattr(tool_loop_support, name), name
        assert name not in tool_loop_support.__all__, name


def test_runner_still_exposes_the_delegated_methods():
    """The upstream instance-level monkeypatch needs these names to resolve."""
    missing = [
        method for method, _ in DELEGATES if not hasattr(ToolLoopAgentRunner, method)
    ]
    assert missing == []


def test_runner_imports_the_support_module_and_keeps_the_completion_hook():
    """The split adds one import and never moves the completion hook itself."""
    tree = ast.parse(RUNNER_PATH.read_text(encoding="utf-8"))

    modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "tool_loop_support" in modules

    definitions = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    assert "_complete_with_assistant_response" in definitions


@pytest.mark.parametrize(("method_name", "function_name"), DELEGATES)
def test_delegate_signatures_match_the_support_functions(method_name, function_name):
    """A delegate is the support function plus ``self``, nothing else.

    Args:
        method_name: Runner method name.
        function_name: Support function name.
    """
    method = inspect.signature(getattr(ToolLoopAgentRunner, method_name))
    function = inspect.signature(getattr(tool_loop_support, function_name))

    # Drop the receiver on both sides: ``self`` on the method, ``runner`` on the
    # support function. Everything after it must be identical.
    method_params = list(method.parameters.values())[1:]
    function_params = list(function.parameters.values())[1:]

    assert [p.name for p in method_params] == [p.name for p in function_params]
    assert [p.kind for p in method_params] == [p.kind for p in function_params]
    assert [p.annotation for p in method_params] == [
        p.annotation for p in function_params
    ]
    assert method.return_annotation == function.return_annotation


def test_read_tool_hint_names_the_configured_tool():
    """A configured read tool is quoted in the spill notice."""
    assert (
        tool_loop_support.read_tool_hint(_RunnerStub(read_tool=_ReadTool()))
        == "`astrbot_file_read_tool`"
    )


def test_read_tool_hint_falls_back_without_a_tool():
    """No read tool means the notice stays generic."""
    assert (
        tool_loop_support.read_tool_hint(_RunnerStub())
        == "the available file-read tool"
    )


def test_preview_keeps_short_content_untouched():
    """Content inside the preview budget is returned verbatim."""
    runner = _RunnerStub(preview_limit=100)

    assert tool_loop_support.truncate_tool_result_preview(
        runner,
        "short result",
        tool_call_id="call_1",
    ) == "short result"


def test_preview_halves_until_it_fits():
    """Oversized content is halved until the estimate fits the budget."""
    runner = _RunnerStub(preview_limit=10)

    preview = tool_loop_support.truncate_tool_result_preview(
        runner,
        "x" * 400,
        tool_call_id="call_1",
    )

    assert len(preview) < 400
    assert runner._tool_result_token_counter.count_tokens(
        [type("M", (), {"content": preview})()]
    ) <= 10


def test_preview_returns_empty_content_unchanged():
    """An empty result never enters the halving loop."""
    assert (
        tool_loop_support.truncate_tool_result_preview(
            _RunnerStub(),
            "",
            tool_call_id="call_1",
        )
        == ""
    )


def test_overflow_write_requires_a_configured_directory():
    """Spilling without a directory fails loudly instead of silently."""
    with pytest.raises(ValueError, match="tool_result_overflow_dir"):
        import asyncio

        asyncio.run(
            tool_loop_support.write_tool_result_overflow_file(
                _RunnerStub(),
                tool_call_id="call_1",
                content="body",
            ),
        )


@pytest.mark.asyncio
async def test_overflow_write_persists_the_content(tmp_path):
    """The spilled file carries the raw content and a stable name prefix."""
    runner = _RunnerStub(overflow_dir=str(tmp_path))

    path = await tool_loop_support.write_tool_result_overflow_file(
        runner,
        tool_call_id="call_1",
        content="body text",
    )

    written = Path(path)
    assert written.exists()
    assert written.read_text(encoding="utf-8") == "body text"
    assert written.name.startswith("call_1_")


@pytest.mark.asyncio
async def test_overflow_write_sanitises_unsafe_call_ids(tmp_path):
    """Path-hostile characters in the call id never escape the directory."""
    runner = _RunnerStub(overflow_dir=str(tmp_path))

    path = await tool_loop_support.write_tool_result_overflow_file(
        runner,
        tool_call_id="../../etc/passwd",
        content="body",
    )

    written = Path(path)
    assert written.parent == tmp_path.resolve()
    assert "/" not in written.name and ".." not in written.name


class _AbortRunner:
    """Runner stand-in for the abort signal and stop state."""

    def __init__(self, stop_requested: bool = False):
        self.run_context = SimpleNamespace(context=None)
        self._abort_signal = asyncio.Event()
        self._stop_requested = stop_requested

    def _is_stop_requested(self) -> bool:
        return self._stop_requested

    async def _close_executor(self, executor) -> None:
        return None


class _AbortRunner:
    """Runner stand-in for the abort signal and stop state."""

    def __init__(self, stop_requested: bool = False):
        self.run_context = SimpleNamespace(context=None)
        self._abort_signal = asyncio.Event()
        self._stop_requested = stop_requested

    def _is_stop_requested(self) -> bool:
        return self._stop_requested

    async def _close_executor(self, executor) -> None:
        return None


class _StreakRunner:
    """Runner stand-in for the repeated-call streak state."""

    def __init__(self):
        self._last_tool_name = None
        self._last_tool_args = None
        self._same_tool_streak = 0


class _NoticeRunner:
    """Runner stand-in carrying the repeated-call notice thresholds."""

    REPEATED_TOOL_NOTICE_L1_THRESHOLD = 2
    REPEATED_TOOL_NOTICE_L2_THRESHOLD = 3
    REPEATED_TOOL_NOTICE_L3_THRESHOLD = 5
    REPEATED_TOOL_NOTICE_L1_TEMPLATE = "L1 {tool_name} {streak}"
    REPEATED_TOOL_NOTICE_L2_TEMPLATE = "L2 {tool_name} {streak}"
    REPEATED_TOOL_NOTICE_L3_TEMPLATE = "L3 {tool_name} {streak}"


def test_streak_increments_for_the_same_tool_and_arguments():
    """An identical call extends the streak instead of restarting it."""
    runner = _StreakRunner()

    assert tool_loop_support.track_tool_call_streak(runner, "t", {"a": 1}) == 1
    assert tool_loop_support.track_tool_call_streak(runner, "t", {"a": 1}) == 2
    assert tool_loop_support.track_tool_call_streak(runner, "t", {"a": 1}) == 3


def test_streak_restarts_when_the_tool_or_arguments_change():
    """A different tool or different arguments resets the streak to one."""
    runner = _StreakRunner()

    assert tool_loop_support.track_tool_call_streak(runner, "t", {"a": 1}) == 1
    assert tool_loop_support.track_tool_call_streak(runner, "t", {"a": 2}) == 1
    assert tool_loop_support.track_tool_call_streak(runner, "other", {"a": 2}) == 1


def test_streak_treats_missing_arguments_as_empty():
    """A tool call without arguments matches an empty argument mapping."""
    runner = _StreakRunner()

    assert tool_loop_support.track_tool_call_streak(runner, "t", None) == 1
    assert tool_loop_support.track_tool_call_streak(runner, "t", {}) == 2


def test_guidance_is_empty_below_the_first_threshold():
    """A first occurrence never gets an escalation notice."""
    assert tool_loop_support.build_repeated_tool_call_guidance(_NoticeRunner(), "t", 1) == ""


def test_guidance_uses_the_l1_template():
    """A streak at the first threshold gets the L1 notice."""
    assert (
        tool_loop_support.build_repeated_tool_call_guidance(_NoticeRunner(), "t", 2)
        == "L1 t 2"
    )


def test_guidance_uses_the_l2_template():
    """A streak at the second threshold gets the L2 notice."""
    assert (
        tool_loop_support.build_repeated_tool_call_guidance(_NoticeRunner(), "t", 3)
        == "L2 t 3"
    )


def test_guidance_uses_the_l3_template():
    """A streak at the third threshold gets the L3 notice."""
    assert (
        tool_loop_support.build_repeated_tool_call_guidance(_NoticeRunner(), "t", 5)
        == "L3 t 5"
    )


@pytest.mark.asyncio
async def test_iter_tool_executor_results_yields_every_result():
    """The helper passes through every executor result in order."""

    async def executor():
        for value in (1, 2, 3):
            yield value

    runner = _AbortRunner()

    assert [
        value async for value in tool_loop_support.iter_tool_executor_results(
            runner,
            executor(),
        )
    ] == [1, 2, 3]


@pytest.mark.asyncio
async def test_iter_tool_executor_results_raises_when_stopped():
    """A stop request wins the race and interrupts the iteration."""

    async def executor():
        yield 1

    runner = _AbortRunner(stop_requested=True)

    with pytest.raises(Exception, match="interrupted"):
        async for _ in tool_loop_support.iter_tool_executor_results(runner, executor()):
            pass


class _AbortRunner:
    """Runner stand-in for the abort signal and stop state."""

    def __init__(self, stop_requested: bool = False):
        self.run_context = SimpleNamespace(context=None)
        self._abort_signal = asyncio.Event()
        self._stop_requested = stop_requested

    def _is_stop_requested(self) -> bool:
        return self._stop_requested

    async def _close_executor(self, executor) -> None:
        return None


class _StreakRunner:
    """Runner stand-in for the repeated-call streak state."""

    def __init__(self):
        self._last_tool_name = None
        self._last_tool_args = None
        self._same_tool_streak = 0


class _NoticeRunner:
    """Runner stand-in carrying the repeated-call notice thresholds."""

    REPEATED_TOOL_NOTICE_L1_THRESHOLD = 2
    REPEATED_TOOL_NOTICE_L2_THRESHOLD = 3
    REPEATED_TOOL_NOTICE_L3_THRESHOLD = 5
    REPEATED_TOOL_NOTICE_L1_TEMPLATE = "L1 {tool_name} {streak}"
    REPEATED_TOOL_NOTICE_L2_TEMPLATE = "L2 {tool_name} {streak}"
    REPEATED_TOOL_NOTICE_L3_TEMPLATE = "L3 {tool_name} {streak}"


def test_streak_increments_for_the_same_tool_and_arguments():
    """An identical call extends the streak instead of restarting it."""
    runner = _StreakRunner()

    assert tool_loop_support.track_tool_call_streak(runner, "t", {"a": 1}) == 1
    assert tool_loop_support.track_tool_call_streak(runner, "t", {"a": 1}) == 2
    assert tool_loop_support.track_tool_call_streak(runner, "t", {"a": 1}) == 3


def test_streak_restarts_when_the_tool_or_arguments_change():
    """A different tool or different arguments resets the streak to one."""
    runner = _StreakRunner()

    assert tool_loop_support.track_tool_call_streak(runner, "t", {"a": 1}) == 1
    assert tool_loop_support.track_tool_call_streak(runner, "t", {"a": 2}) == 1
    assert tool_loop_support.track_tool_call_streak(runner, "other", {"a": 2}) == 1


def test_streak_treats_missing_arguments_as_empty():
    """A tool call without arguments matches an empty argument mapping."""
    runner = _StreakRunner()

    assert tool_loop_support.track_tool_call_streak(runner, "t", None) == 1
    assert tool_loop_support.track_tool_call_streak(runner, "t", {}) == 2


def test_guidance_is_empty_below_the_first_threshold():
    """A first occurrence never gets an escalation notice."""
    assert tool_loop_support.build_repeated_tool_call_guidance(_NoticeRunner(), "t", 1) == ""


def test_guidance_uses_the_l1_template():
    """A streak at the first threshold gets the L1 notice."""
    assert (
        tool_loop_support.build_repeated_tool_call_guidance(_NoticeRunner(), "t", 2)
        == "L1 t 2"
    )


def test_guidance_uses_the_l2_template():
    """A streak at the second threshold gets the L2 notice."""
    assert (
        tool_loop_support.build_repeated_tool_call_guidance(_NoticeRunner(), "t", 3)
        == "L2 t 3"
    )


def test_guidance_uses_the_l3_template():
    """A streak at the third threshold gets the L3 notice."""
    assert (
        tool_loop_support.build_repeated_tool_call_guidance(_NoticeRunner(), "t", 5)
        == "L3 t 5"
    )


@pytest.mark.asyncio
async def test_iter_tool_executor_results_yields_every_result():
    """The helper passes through every executor result in order."""

    async def executor():
        for value in (1, 2, 3):
            yield value

    runner = _AbortRunner()

    assert [
        value async for value in tool_loop_support.iter_tool_executor_results(
            runner,
            executor(),
        )
    ] == [1, 2, 3]


@pytest.mark.asyncio
async def test_iter_tool_executor_results_raises_when_stopped():
    """A stop request wins the race and interrupts the iteration."""

    async def executor():
        yield 1

    runner = _AbortRunner(stop_requested=True)

    with pytest.raises(Exception, match="interrupted"):
        async for _ in tool_loop_support.iter_tool_executor_results(runner, executor()):
            pass
