"""Calling the bot is detected for quoted replies too, not just for @.

``internal.py`` uses this check to decide whether a message that carries no
written text still counts as "the user summoned the bot", which is what earns it
the fallback prompt. It used to look at ``At`` components only, so quoting one
of the bot's own messages and typing nothing left the request with an empty
prompt. The shared ``mentions_self`` helper already covers both shapes.
"""

from types import SimpleNamespace

from astrbot.core.message.components import At, Plain, Reply
from astrbot.core.utils.direct_turns import mentions_self

BOT_ID = "10001"
OTHER_ID = "10002"


def _event(*components, self_id=BOT_ID):
    return SimpleNamespace(
        get_self_id=lambda: self_id,
        get_messages=lambda: list(components),
    )


def test_at_targeting_the_bot_counts():
    assert mentions_self(_event(At(qq=BOT_ID))) is True


def test_at_targeting_someone_else_does_not_count():
    assert mentions_self(_event(At(qq=OTHER_ID))) is False


def test_quoting_the_bot_counts():
    assert mentions_self(_event(Reply(id="1", sender_id=BOT_ID))) is True


def test_quoting_someone_else_does_not_count():
    assert mentions_self(_event(Reply(id="1", sender_id=OTHER_ID))) is False


def test_plain_text_alone_does_not_count():
    assert mentions_self(_event(Plain("hello"))) is False


def test_empty_message_does_not_count():
    assert mentions_self(_event()) is False


def test_event_without_self_id_does_not_count():
    event = SimpleNamespace(get_messages=lambda: [At(qq=BOT_ID)])
    assert mentions_self(event) is False


def test_mention_anywhere_in_the_chain_counts():
    event = _event(Plain("look"), Reply(id="1", sender_id=BOT_ID))
    assert mentions_self(event) is True
