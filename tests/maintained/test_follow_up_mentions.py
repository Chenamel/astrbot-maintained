"""Shared At/Reply "mentions another account" predicate (T8-12 Step 1).

``follow_up.try_capture_follow_up`` used to carry a verbatim copy of the
predicate that lives in ``direct_turns``, with a different ``self_id``
fallback. Both now call ``direct_turns.mentions_other``; these tests pin the
shared behaviour and prove the refactor did not change what either caller sees.
"""

from __future__ import annotations

from astrbot.core.message.components import At, Plain, Reply
from astrbot.core.pipeline.process_stage import follow_up
from astrbot.core.utils import direct_turns

SELF_ID = "10001"
OTHER_ID = "99999"


class _Event:
    """Minimal event stand-in carrying a component list."""

    def __init__(self, components, self_id=SELF_ID, sender_id="20002"):
        self._components = list(components)
        self._self_id = self_id
        self._sender_id = sender_id
        self.unified_msg_origin = "platform:group:1"

    def get_messages(self):
        return self._components

    def get_self_id(self):
        return self._self_id

    def get_sender_id(self):
        return self._sender_id

    def get_message_str(self):
        return ""

    def get_message_outline(self):
        return ""


class _EventWithoutSelfId(_Event):
    """Event stand-in that cannot report the bot id."""

    get_self_id = None  # type: ignore[assignment]


def _legacy_follow_up_predicate(event) -> bool:
    """The predicate as it read before Step 1 deduplicated it."""
    self_id = str(event.get_self_id()) if hasattr(event, "get_self_id") else ""
    return any(
        isinstance(component, At)
        and str(component.qq) != self_id
        or isinstance(component, Reply)
        and str(component.sender_id) != self_id
        for component in event.get_messages()
    )


def _legacy_direct_turns_predicate(event) -> bool:
    """The ``direct_turns`` copy as it read before Step 1."""
    self_id = str(event.get_self_id())
    return any(
        isinstance(component, At)
        and str(component.qq) != self_id
        or isinstance(component, Reply)
        and str(component.sender_id) != self_id
        for component in event.get_messages()
    )


class _RecordingRunners(dict):
    """Runner registry recording every lookup made against it."""

    def __init__(self):
        super().__init__()
        self.lookups: list[str] = []

    def get(self, key, default=None):  # noqa: D102 - dict override
        self.lookups.append(key)
        return default


def test_self_id_of_reads_the_event_id():
    assert direct_turns.self_id_of(_Event([])) == SELF_ID


def test_self_id_of_falls_back_to_empty_without_the_accessor():
    assert direct_turns.self_id_of(_EventWithoutSelfId([])) == ""


def test_mentions_other_detects_an_at_to_someone_else():
    assert direct_turns.mentions_other(_Event([At(qq=OTHER_ID)]))
    assert not direct_turns.mentions_other(_Event([At(qq=SELF_ID)]))
    assert not direct_turns.mentions_other(_Event([Plain(text="hi")]))


def test_mentions_other_detects_a_reply_to_someone_else():
    assert direct_turns.mentions_other(
        _Event([Reply(id="1", sender_id=OTHER_ID)]),
    )
    assert not direct_turns.mentions_other(
        _Event([Reply(id="1", sender_id=SELF_ID)]),
    )


def test_mentions_self_is_the_complement_of_mentions_other():
    event = _Event([At(qq=SELF_ID), Plain(text="hi")])
    assert direct_turns.mentions_self(event)
    assert not direct_turns.mentions_other(event)


def test_shared_predicate_matches_both_legacy_copies():
    cases = [
        [],
        [Plain(text="hello")],
        [At(qq=SELF_ID)],
        [At(qq=OTHER_ID)],
        [Reply(id="1", sender_id=SELF_ID)],
        [Reply(id="1", sender_id=OTHER_ID)],
        [Plain(text="hi"), At(qq=SELF_ID), At(qq=OTHER_ID)],
    ]
    for components in cases:
        event = _Event(components)
        assert direct_turns.mentions_other(event) == _legacy_follow_up_predicate(event)
        assert (
            direct_turns.mentions_other(event) == _legacy_direct_turns_predicate(event)
        )


def test_capture_skips_the_runner_lookup_when_another_account_is_mentioned(
    monkeypatch,
):
    runners = _RecordingRunners()
    monkeypatch.setattr(follow_up, "_ACTIVE_AGENT_RUNNERS", runners)

    assert follow_up.try_capture_follow_up(_Event([At(qq=OTHER_ID)])) is None
    assert runners.lookups == []


def test_capture_reaches_the_runner_lookup_when_only_the_bot_is_mentioned(monkeypatch):
    runners = _RecordingRunners()
    monkeypatch.setattr(follow_up, "_ACTIVE_AGENT_RUNNERS", runners)

    assert follow_up.try_capture_follow_up(_Event([At(qq=SELF_ID)])) is None
    assert runners.lookups == ["platform:group:1"]
