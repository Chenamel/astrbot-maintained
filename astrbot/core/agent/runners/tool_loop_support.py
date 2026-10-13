"""Oversized tool-result helpers extracted from the tool-loop agent runner.

T8-12 splits the 2000-line runner into focused modules. The runner keeps thin
delegating methods for these helpers so that instance-level patches in the
upstream tests keep working; every helper takes the runner as its first
argument instead of importing it, which keeps this module free of cycles.
"""

import asyncio
import uuid
from pathlib import Path

from ..message import Message

__all__ = [
    "read_tool_hint",
    "truncate_tool_result_preview",
    "write_tool_result_overflow_file",
]


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
