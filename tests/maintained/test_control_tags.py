"""Tests for the outgoing control-tag sanitizer."""

from __future__ import annotations

from astrbot.core.message.components import Plain
from astrbot.core.utils.control_tags import strip_control_tags


def _texts(chain: list) -> list[str]:
    return [c.text for c in chain if isinstance(c, Plain)]


def test_strips_quote_tag_and_keeps_sentence() -> None:
    chain = [Plain(text='<quote id="1824373648"/>来了来了')]
    assert strip_control_tags(chain) == 1
    assert _texts(chain) == ["来了来了"]


def test_strips_mention_and_refuse() -> None:
    chain = [Plain(text='<mention id="1"/>你好'), Plain(text="<refuse/>")]
    assert strip_control_tags(chain) == 2
    assert _texts(chain) == ["你好", ""]


def test_clean_text_untouched() -> None:
    chain = [Plain(text="正常一句话，里面提到 quote 这个词也不算标签")]
    assert strip_control_tags(chain) == 0
    assert _texts(chain)[0].startswith("正常一句话")


def test_does_not_touch_unknown_or_code_like_tags() -> None:
    # Only known control tags are removed; arbitrary XML/HTML must survive.
    chain = [Plain(text='<div class="x">内容</div>')]
    assert strip_control_tags(chain) == 0
    assert _texts(chain)[0] == '<div class="x">内容</div>'


def test_non_plain_components_ignored() -> None:
    class Fake:
        pass

    chain = [Fake(), Plain(text="<quote id='9'/>说明")]
    assert strip_control_tags(chain) == 1
