"""Who said this? The bot's own words must not read like a stranger's.

A quoted message travels with its author's nickname, and the bot's nickname is
just another name -- nothing in the prompt says it owns that name. So when a
user quotes the bot's earlier reply, the model reads a third party's sentence
and answers accordingly: it explains "that receipt came from a permission
plugin" instead of "what I said there was…". Comparing ids settles it.
"""

import pytest

from astrbot.core.message.components import Plain, Reply
from astrbot.core.platform.astr_message_event import AstrMessageEvent

BOT_ID = "3944860270"


class _View:
    """Just enough of an event to reach the outline helpers."""

    _quote_speaker = AstrMessageEvent._quote_speaker
    _outline_chain = AstrMessageEvent._outline_chain
    get_self_id = AstrMessageEvent.get_self_id

    def __init__(self, self_id: str) -> None:
        self.message_obj = type("Obj", (), {"self_id": self_id})()


def _reply(sender_id: str, nickname: str, text: str) -> Reply:
    return Reply(
        id="1",
        chain=[Plain(text=text)],
        sender_id=sender_id,
        sender_nickname=nickname,
        message_str=text,
    )


def test_our_own_quoted_message_is_attributed_to_me():
    chain = [_reply(BOT_ID, "hesder", "管理命令仅管理员可用。")]

    outline = _View(BOT_ID)._outline_chain(chain)

    assert "我" in outline
    assert "hesder" not in outline


def test_someone_elses_quoted_message_keeps_their_name():
    chain = [_reply("428653410", "卤管王", "这个你可以关掉吗")]

    outline = _View(BOT_ID)._outline_chain(chain)

    assert "卤管王" in outline
    assert "我" not in outline


def test_an_unnamed_author_is_not_left_blank():
    chain = [_reply("", "", "没有昵称的消息")]

    assert "未知" in _View(BOT_ID)._outline_chain(chain)


def test_a_missing_self_id_never_claims_authorship():
    """Without a self id there is nothing to compare, so nobody becomes "我"."""
    chain = [_reply(BOT_ID, "hesder", "内容")]

    assert "hesder" in _View("")._outline_chain(chain)


@pytest.mark.parametrize("text", ["", None])
def test_a_quote_without_text_still_renders(text):
    reply = _reply(BOT_ID, "hesder", text or "")
    reply.message_str = text

    assert _View(BOT_ID)._outline_chain([reply]) == "[引用消息]"
