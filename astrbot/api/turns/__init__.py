"""Direct turn state, as seen by plugins.

A *direct turn* groups messages sent by the same account in quick succession
into one request, and supersedes the previous turn when a newer message
arrives. The core owns that state machine; this module only exposes read
access plus the two reset hooks a plugin needs for its own lifecycle.

Public surface (see ``docs/maintained/api-contract.md``):

- :func:`available`
- :func:`is_current`
- :func:`mark_sent`
- :func:`turn_version`
- :func:`merged_text`
- :func:`merged_image_urls`
- :func:`reset`
- :func:`reset_all`

When the core-side support is absent every function degrades to a safe value
instead of raising, so a plugin can use this module unconditionally.
"""

from __future__ import annotations

import logging
from typing import Any

from astrbot.api._bridge import resolve

logger = logging.getLogger("astrbot")

__all__ = [
    "available",
    "is_current",
    "mark_sent",
    "merged_image_urls",
    "merged_text",
    "reset",
    "reset_all",
    "turn_version",
]

_MODULE = "astrbot.core.utils.direct_turns"


def _extra(event: Any, key: str, default: Any = None) -> Any:
    """Read an event extra defensively."""
    getter = getattr(event, "get_extra", None)
    if not callable(getter):
        return default
    try:
        value = getter(key)
    except Exception:  # noqa: BLE001 - event contract is duck-typed
        return default
    return default if value is None else value


def _coordinator() -> Any:
    """Return the process-wide turn coordinator, or ``None`` when absent."""
    return resolve(_MODULE, "coordinator", None)


def available() -> bool:
    """Return whether the core-side direct turn support is installed."""
    return _coordinator() is not None


def is_current(event: Any) -> bool:
    """Return whether an event still represents the current turn.

    Fails open: if the check itself is unavailable or raises, the event is
    reported as current so that a user reply is never silently dropped.

    Args:
        event: The ``AstrMessageEvent`` to inspect.

    Returns:
        ``True`` when the event may still be delivered.
    """
    checker = resolve(_MODULE, "is_current", None)
    if checker is None:
        return True
    try:
        return bool(checker(event))
    except Exception as exc:  # noqa: BLE001 - never block delivery on a check error
        logger.warning("direct turn is_current check failed: %s", exc)
        return True


def mark_sent(event: Any) -> None:
    """Record that the turn's reply has been sent.

    Args:
        event: The event whose turn completed delivery.
    """
    marker = resolve(_MODULE, "mark_sent", None)
    if marker is None:
        return
    try:
        marker(event)
    except Exception as exc:  # noqa: BLE001 - bookkeeping must not break sending
        logger.warning("direct turn mark_sent failed: %s", exc)


def turn_version(event: Any) -> int | None:
    """Return the turn version attached to an event, if any.

    Args:
        event: The event to inspect.

    Returns:
        The version number, or ``None`` when the event carries no turn.
    """
    value = _extra(event, "_direct_turn_version")
    return value if isinstance(value, int) else None


def merged_text(event: Any) -> str:
    """Return the merged text of the turn's messages.

    Args:
        event: The event to inspect.

    Returns:
        The merged text, or an empty string when there is none.
    """
    value = _extra(event, "_direct_turn_text")
    return value if isinstance(value, str) else ""


def merged_image_urls(event: Any) -> list[str]:
    """Return the merged image URLs of the turn's messages.

    Args:
        event: The event to inspect.

    Returns:
        A list of URL strings, empty when there are none.
    """
    value = _extra(event, "_direct_turn_image_urls")
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, str)]
    return []


def reset(unified_msg_origin: str) -> bool:
    """Drop the turn state of one session.

    Args:
        unified_msg_origin: The session identifier to clear.

    Returns:
        ``True`` when the state was dropped.
    """
    coordinator = _coordinator()
    if coordinator is None:
        return False
    try:
        coordinator.reset(unified_msg_origin)
    except Exception as exc:  # noqa: BLE001 - reset is best effort
        logger.warning("direct turn reset failed: %s", exc)
        return False
    return True


def reset_all() -> bool:
    """Drop all turn state.

    Returns:
        ``True`` when the state was dropped.
    """
    coordinator = _coordinator()
    if coordinator is None:
        return False
    try:
        coordinator.reset_all()
    except Exception as exc:  # noqa: BLE001 - reset is best effort
        logger.warning("direct turn reset_all failed: %s", exc)
        return False
    return True
