"""The aiocqhttp aggregation window is configurable and can be switched off.

The quiet window is a fork addition: it costs every aiocqhttp message a few
seconds before the model is even called, which upstream never pays. The knob
under test lets a deployment opt out without losing the code path.

The subtle part is that a zero-length window must also stop turn tracking. If
it only shortened the wait, the first message would be released instantly while
the next one still invalidated it -- strictly worse than not aggregating.
"""

from types import SimpleNamespace

import pytest

from astrbot.core.utils.direct_turns import (
    DEFAULT_QUIET_SEC,
    DirectTurnCoordinator,
)


class _Clock:
    """Monotonic clock that only advances when a test advances it."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _event(platform="aiocqhttp", sender="10001"):
    """Return a duck-typed aiocqhttp message event with an extras store."""
    store = {}

    def set_extra(key, value):
        store[key] = value

    return SimpleNamespace(
        unified_msg_origin="umo",
        get_platform_name=lambda: platform,
        get_sender_id=lambda: sender,
        get_messages=lambda: [],
        message_obj=SimpleNamespace(message_id="1"),
        get_message_str=lambda: "hi",
        get_extra=lambda key, default=None: store.get(key, default),
        set_extra=set_extra,
        store=store,
        stop_event=lambda: None,
        is_private_chat=lambda: True,
        is_at_or_wake_command=True,
        is_stopped=lambda: False,
    )


def _coordinator(clock=None):
    return DirectTurnCoordinator(clock=clock or _Clock())


def test_default_window_keeps_aggregation_on():
    coordinator = _coordinator()
    assert coordinator.enabled is True
    assert coordinator.quiet_sec == DEFAULT_QUIET_SEC


def test_zero_window_disables_eligibility():
    coordinator = _coordinator()
    coordinator.configure(0)
    assert coordinator.enabled is False
    assert coordinator.eligible(_event()) is False


def test_zero_window_stops_turn_tracking():
    coordinator = _coordinator()
    coordinator.configure(0)
    event = _event()
    coordinator.observe(event)
    assert "_direct_turn_state" not in event.store
    assert coordinator.turns == {}


@pytest.mark.asyncio
async def test_collect_releases_immediately_when_disabled():
    clock = _Clock()
    coordinator = DirectTurnCoordinator(clock=clock)
    coordinator.configure(0)
    assert await coordinator.collect(_event()) is True
    assert clock.now == 0.0


def test_disabled_turns_never_invalidate_each_other():
    coordinator = _coordinator()
    coordinator.configure(0)
    first = _event()
    second = _event()
    coordinator.observe(first)
    coordinator.observe(second)
    assert "_direct_turn_state" not in first.store
    assert "_direct_turn_state" not in second.store


@pytest.mark.parametrize("value", [None, True, -1, "4", object()])
def test_invalid_values_leave_the_window_unchanged(value):
    coordinator = _coordinator()
    coordinator.configure(value)
    assert coordinator.enabled is True
    assert coordinator.quiet_sec == DEFAULT_QUIET_SEC


def test_positive_value_restores_aggregation():
    coordinator = _coordinator()
    coordinator.configure(0)
    coordinator.configure(2)
    assert coordinator.enabled is True
    assert coordinator.quiet_sec == 2.0
    assert coordinator.eligible(_event()) is True


def test_non_aiocqhttp_events_stay_ineligible():
    coordinator = _coordinator()
    assert coordinator.eligible(_event(platform="qq_official")) is False


# --------------------------------------------------------------------------
# Per-conversation windows: one process, several bots
# --------------------------------------------------------------------------


def test_windows_are_kept_per_conversation():
    """A second bot's profile must not rewrite the first bot's window.

    The coordinator is a process-wide singleton, so a shared field meant "the
    last message sets the wait for everyone". Two bots with different profiles
    quietly fought over it.
    """
    coordinator = _coordinator()

    coordinator.configure(8.0, "umo-a")
    coordinator.configure(0.0, "umo-b")

    assert coordinator.window_for("umo-a") == (8.0, True)
    assert coordinator.window_for("umo-b") == (0.0, False)


def test_an_unseen_conversation_falls_back_to_the_default():
    coordinator = _coordinator()
    coordinator.configure(6.0)

    assert coordinator.window_for("umo-never-seen") == (6.0, True)


def test_configure_without_an_origin_still_sets_the_default():
    """Tests and single-bot deployments use the flat form; it must keep working."""
    coordinator = _coordinator()

    coordinator.configure(0.0)

    assert coordinator.quiet_sec == 0.0
    assert coordinator.enabled is False


def test_a_disabled_conversation_does_not_track_turns():
    coordinator = _coordinator()
    coordinator.configure(0.0, "umo-a")

    event = _event()
    event.unified_msg_origin = "umo-a"

    assert coordinator.eligible(event) is False
    assert coordinator.turns == {}


def test_invalid_values_do_not_erase_a_window():
    coordinator = _coordinator()
    coordinator.configure(5.0, "umo-a")

    for bad in (None, "3", -1, True):
        coordinator.configure(bad, "umo-a")

    assert coordinator.window_for("umo-a") == (5.0, True)
