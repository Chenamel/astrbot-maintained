"""Output-format guidance injected for plain-text chat platforms.

QQ renders messages as plain text: markdown arrives as literal asterisks and
pipes, which reads worse than no formatting at all. The prompt asks for plain
sentences while keeping fenced code blocks, since those are preserved intact by
the splitter and carry real content.
"""

from types import SimpleNamespace

import pytest

from astrbot.core.astr_main_agent import (
    _PLAIN_TEXT_OUTPUT_PROMPT,
    _plain_text_output_prompt,
)


def _event(platform_name: str | None) -> SimpleNamespace:
    """Build the smallest event the helper reads."""
    return SimpleNamespace(get_platform_name=lambda: platform_name)


@pytest.mark.parametrize("platform", ["aiocqhttp", "qqofficial", "AIOcqhttp"])
def test_plain_text_platforms_get_guidance(platform):
    assert _plain_text_output_prompt(_event(platform)) == _PLAIN_TEXT_OUTPUT_PROMPT


@pytest.mark.parametrize("platform", ["webchat", "telegram", "wecom", None, ""])
def test_markdown_platforms_get_nothing(platform):
    assert _plain_text_output_prompt(_event(platform)) == ""


def test_guidance_forbids_markdown_but_allows_code_fences():
    """The rule must not ban code blocks: the splitter protects them."""
    assert "no headings" in _PLAIN_TEXT_OUTPUT_PROMPT
    assert "no tables" in _PLAIN_TEXT_OUTPUT_PROMPT
    assert "Fenced code blocks" in _PLAIN_TEXT_OUTPUT_PROMPT
    assert "exception" in _PLAIN_TEXT_OUTPUT_PROMPT
