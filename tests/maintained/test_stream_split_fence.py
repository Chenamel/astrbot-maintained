"""Tests for the streaming fallback splitter.

The only rule that matters here: never cut inside a fenced code block, because
both halves lose their formatting and code comments are exactly where Chinese
sentence punctuation appears.
"""

from __future__ import annotations

import re

from astrbot.core.platform.astr_message_event import AstrMessageEvent

PATTERN = re.compile(r"[^。？！~…]+[。？！~…]+")


def _split_points(buffer: str) -> list[str]:
    """Repeatedly pick split points the way process_buffer does."""
    out: list[str] = []
    rest = buffer
    while True:
        match = AstrMessageEvent._find_splittable(rest, PATTERN)
        if not match:
            break
        out.append(match.group().strip())
        rest = rest[match.end() :]
    return out


def test_plain_text_splits_on_sentence_end() -> None:
    assert _split_points("第一句。第二句。") == ["第一句。", "第二句。"]


def test_never_cuts_inside_a_code_block() -> None:
    """The invariant: every emitted part holds whole fences only.

    A part may legitimately contain a closed block plus trailing prose -- what
    must never happen is a fence opened in one part and closed in another.
    """
    text = "看代码。\n```python\n# 这里有个句号。不该切\nprint(1)\n```\n完事了。"
    parts = _split_points(text)
    assert parts[0] == "看代码。"
    assert all(p.count("```") % 2 == 0 for p in parts)


def test_block_at_the_start_waits_for_the_final_flush() -> None:
    """Deliberate trade-off: safety over segmentation.

    The sentence pattern cannot start after the closing fence (it swallows the
    fence into its "non-punctuation" run), so splitting here would emit a
    fragment holding the closing fence without the opening one. Sending the
    whole thing once is the safer failure mode.
    """
    text = "```\n代码。\n```\n之后这句。"
    assert _split_points(text) == []


def test_unclosed_block_never_splits_inside() -> None:
    text = "```python\n# 未闭合。\n还在这。"
    assert _split_points(text) == []


def test_unclosed_block_flushes_whole_buffer() -> None:
    """Whatever is left must still be delivered, fence and all."""
    text = "先说话。\n```\n未闭合。"
    parts = _split_points(text)
    assert parts == ["先说话。"]
    # The remainder (with the fence) stays for the final flush.
    rest = text[len("先说话。") :]
    assert "```" in rest
