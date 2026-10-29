"""A group message containing newlines must not split the log into many lines.

The log copy is escaped; the event itself is untouched, so plugins still see the
original text. That distinction is what makes this safe to enable by default.
"""

import pytest

from astrbot.core.event_bus import NEWLINE_MARK, _collapse_newlines


def test_newline_becomes_a_visible_mark():
    assert _collapse_newlines("第一行\n第二行") == f"第一行{NEWLINE_MARK}第二行"


def test_crlf_counts_as_one_newline():
    """Replacing \\n first would leave a stray \\r and produce two marks."""
    assert _collapse_newlines("a\r\nb") == f"a{NEWLINE_MARK}b"


def test_lone_carriage_return_is_also_marked():
    assert _collapse_newlines("a\rb") == f"a{NEWLINE_MARK}b"


def test_plain_text_is_unchanged():
    assert _collapse_newlines("就是一句普通的话") == "就是一句普通的话"


def test_multiple_newlines_each_get_a_mark():
    assert _collapse_newlines("a\n\nb") == f"a{NEWLINE_MARK}{NEWLINE_MARK}b"


@pytest.mark.parametrize("mark", [NEWLINE_MARK])
def test_mark_is_visible_but_not_a_control_character(mark):
    """It must survive a terminal and be obvious to a human reader."""
    assert mark.isprintable()
    assert mark not in ("\n", "\r")


def test_control_characters_are_dropped():
    """They split a log line exactly like a newline, but carry no meaning."""
    messy = "签到" + chr(6) + chr(18) + chr(4) + "tefh" + chr(5) + chr(3) + "打卡"

    assert _collapse_newlines(messy) == "签到tefh打卡"


def test_newline_and_control_characters_together():
    text = "第一行" + chr(10) + "第二行" + chr(7) + "第三行"

    assert _collapse_newlines(text) == f"第一行{NEWLINE_MARK}第二行第三行"
