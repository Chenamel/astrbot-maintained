"""Helpers extracted from the tool-loop agent runner by T8-12.

The module grew in three steps: Step 4a moved the oversized tool-result
helpers here, Step 4b the tool-loop iteration helpers (plus the interrupt
exception and result type they need), and Step 4c the tool sanitize and
re-query helpers.

The runner keeps thin delegating methods for all of them so that instance
level patches and direct method calls in the upstream tests keep working.
Every helper that needs runner state takes the runner as its first argument
instead of importing it, which keeps this module free of cycles; helpers that
need no runner state stay plain functions.
"""

import asyncio
import copy
import typing as T
import uuid
from contextlib import suppress
from pathlib import Path

from astrbot.core.agent.tool import ToolSet
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.utils.direct_turns import is_current

from ..message import Message

__all__ = [
    "build_repeated_tool_call_guidance",
    "build_tool_requery_context",
    "build_tool_subset",
    "has_meaningful_assistant_reply",
    "iter_tool_executor_results",
    "read_tool_hint",
    "sanitize_malformed_tool_calls",
    "track_tool_call_streak",
    "truncate_tool_result_preview",
    "write_tool_result_overflow_file",
]


class _ToolExecutionInterrupted(Exception):
    """Raised when a running tool call is interrupted by a stop request."""


ToolExecutorResultT = T.TypeVar("ToolExecutorResultT")


def read_tool_hint(runner) -> str:
    """Describe the file-read tool available for spilled tool results.

    Args:
        runner: The agent runner whose read tool is described.

    Returns:
        A backticked tool name, or a generic hint when no read tool is set.
    """
    if runner.read_tool is not None:
        return f"`{runner.read_tool.name}`"
    return "the available file-read tool"


async def write_tool_result_overflow_file(
    runner,
    *,
    tool_call_id: str,
    content: str,
) -> str:
    """Write an oversized tool result to a per-call file off the event loop.

    Args:
        runner: The agent runner owning the overflow directory.
        tool_call_id: Identifier of the tool call the result belongs to.
        content: Raw tool result text to spill.

    Returns:
        Absolute path of the written overflow file.

    Raises:
        ValueError: When no overflow directory is configured on the runner.
    """
    if runner.tool_result_overflow_dir is None:
        raise ValueError("tool_result_overflow_dir is not configured")

    overflow_dir = Path(runner.tool_result_overflow_dir).resolve(strict=False)
    safe_tool_call_id = (
        "".join(
            ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in tool_call_id
        ).strip("._")
        or "tool_call"
    )
    file_name = f"{safe_tool_call_id}_{uuid.uuid4().hex[:8]}.txt"
    overflow_path = overflow_dir / file_name

    def _run() -> str:
        overflow_dir.mkdir(parents=True, exist_ok=True)
        overflow_path.write_text(content, encoding="utf-8")
        return str(overflow_path)

    return await asyncio.to_thread(_run)


def truncate_tool_result_preview(
    runner,
    content: str,
    *,
    tool_call_id: str,
) -> str:
    """Halve a tool result until its estimated size fits the inline preview.

    Args:
        runner: The agent runner owning the token counter and preview limit.
        content: Raw tool result text to shorten.
        tool_call_id: Identifier used while estimating the token count.

    Returns:
        The longest prefix of ``content`` within the preview token budget.
    """
    preview = content
    while preview:
        estimated_tokens = runner._tool_result_token_counter.count_tokens(
            [Message(role="tool", content=preview, tool_call_id=tool_call_id)]
        )
        if estimated_tokens <= runner.TOOL_RESULT_PREVIEW_MAX_ESTIMATED_TOKENS:
            return preview
        next_len = len(preview) // 2
        if next_len <= 0:
            break
        preview = preview[:next_len]
    return preview


def track_tool_call_streak(
    runner,
    tool_name: str,
    tool_args: dict[str, T.Any] | None,
) -> int:
    """Track consecutive tool calls with the same name and arguments.

    Args:
        runner: The agent runner owning the streak state.
        tool_name: Name of the called tool.
        tool_args: Arguments passed to the tool.

    Returns:
        Number of consecutive calls with the same name and arguments.
    """
    normalized_args = {} if tool_args is None else tool_args
    if (
        tool_name == runner._last_tool_name
        and normalized_args == runner._last_tool_args
    ):
        runner._same_tool_streak += 1
    else:
        runner._last_tool_name = tool_name
        runner._last_tool_args = copy.deepcopy(normalized_args)
        runner._same_tool_streak = 1
    return runner._same_tool_streak


def build_repeated_tool_call_guidance(runner, tool_name: str, streak: int) -> str:
    """Return the escalation notice for a repeated identical tool call.

    Args:
        runner: The agent runner owning the notice templates and thresholds.
        tool_name: Name of the repeated tool.
        streak: Number of consecutive identical calls.

    Returns:
        The notice for the highest threshold the streak reached, or an empty
        string when the streak is still below the first threshold.
    """
    if streak < runner.REPEATED_TOOL_NOTICE_L1_THRESHOLD:
        return ""

    if streak >= runner.REPEATED_TOOL_NOTICE_L3_THRESHOLD:
        return runner.REPEATED_TOOL_NOTICE_L3_TEMPLATE.format(
            tool_name=tool_name,
            streak=streak,
        )

    if streak >= runner.REPEATED_TOOL_NOTICE_L2_THRESHOLD:
        return runner.REPEATED_TOOL_NOTICE_L2_TEMPLATE.format(
            tool_name=tool_name,
            streak=streak,
        )

    return runner.REPEATED_TOOL_NOTICE_L1_TEMPLATE.format(
        tool_name=tool_name,
        streak=streak,
    )


async def iter_tool_executor_results(
    runner,
    executor: T.AsyncGenerator[ToolExecutorResultT, None],
) -> T.AsyncGenerator[ToolExecutorResultT, None]:
    """Yield tool executor results, aborting as soon as a stop request wins.

    Args:
        runner: The agent runner owning the abort signal and stop state.
        executor: Async generator of tool executor results.

    Yields:
        Every result produced by the executor until it is exhausted.

    Raises:
        _ToolExecutionInterrupted: When a stop request arrives first.
    """

    async def _next_executor_result() -> ToolExecutorResultT:
        return await anext(executor)

    while True:
        event = getattr(runner.run_context.context, "event", None)
        stale_reserved_tool = event is not None and not is_current(event)
        if runner._is_stop_requested() and not stale_reserved_tool:
            await runner._close_executor(executor)
            raise _ToolExecutionInterrupted(
                "Tool execution interrupted before reading the next tool result."
            )

        next_result_task = asyncio.create_task(_next_executor_result())
        abort_task = asyncio.create_task(runner._abort_signal.wait())
        try:
            done, _ = await asyncio.wait(
                {next_result_task, abort_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if abort_task in done:
                if event is not None and not is_current(event):
                    # A started operation must finish once; replacement reuses its result.
                    try:
                        yield await next_result_task
                    except StopAsyncIteration:
                        return
                    continue
                if not next_result_task.done():
                    next_result_task.cancel()
                    with suppress(asyncio.CancelledError, StopAsyncIteration):
                        await next_result_task

                await runner._close_executor(executor)

                raise _ToolExecutionInterrupted(
                    "Tool execution interrupted by a stop request."
                )

            try:
                yield next_result_task.result()
            except StopAsyncIteration:
                return
        finally:
            if not abort_task.done():
                abort_task.cancel()
                with suppress(asyncio.CancelledError):
                    await abort_task


def sanitize_malformed_tool_calls(runner, llm_resp: LLMResponse) -> None:
    """Normalize malformed tool call names.

    Args:
        runner: The agent runner owning the placeholder name.
        llm_resp: The LLM response whose tool call lists should be sanitized.
    """
    llm_resp.tools_call_name = [
        runner.MALFORMED_TOOL_NAME_PLACEHOLDER
        if tool_name is None or tool_name.strip() == ""
        else tool_name
        for tool_name in llm_resp.tools_call_name
    ]


def build_tool_requery_context(
    runner,
    tool_names: list[str],
    extra_instruction: str | None = None,
) -> list[dict[str, T.Any]]:
    """Build contexts for re-querying the LLM with param-only tool schemas.

    Args:
        runner: The agent runner owning the conversation messages.
        tool_names: Tool names to re-query.
        extra_instruction: Optional instruction appended to the template.

    Returns:
        Dumped conversation messages followed by one user instruction message.
    """
    contexts: list[dict[str, T.Any]] = []
    for msg in runner.run_context.messages:
        if hasattr(msg, "model_dump"):
            contexts.append(msg.model_dump())  # type: ignore[call-arg]
        elif isinstance(msg, dict):
            contexts.append(copy.deepcopy(msg))
    instruction = runner.SKILLS_LIKE_REQUERY_INSTRUCTION_TEMPLATE.format(
        tool_names=", ".join(tool_names)
    )
    if extra_instruction:
        instruction = f"{instruction}\n{extra_instruction}"
    contexts.append({"role": "user", "content": instruction})
    return contexts


def has_meaningful_assistant_reply(llm_resp: LLMResponse) -> bool:
    """Return whether the response carries non-empty assistant text.

    Args:
        llm_resp: The LLM response to inspect.

    Returns:
        True when the completion text has non-whitespace content.
    """
    text = (llm_resp.completion_text or "").strip()
    return bool(text)


def build_tool_subset(tool_set: ToolSet, tool_names: list[str]) -> ToolSet:
    """Build a subset of tools from the given tool set based on tool names.

    Args:
        tool_set: Source tool set.
        tool_names: Names to keep, in this order.

    Returns:
        A new tool set holding every matched tool.
    """
    subset = ToolSet()
    for name in tool_names:
        tool = tool_set.get_tool(name)
        if tool:
            subset.add_tool(tool)
    return subset
