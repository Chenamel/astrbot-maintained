"""Named access to the event extras the core shares with plugins.

The core used to read these keys inline: ``event.get_extra("_enhance_xxx")``.
That made the core depend on one particular plugin's private vocabulary, and it
failed quietly -- a renamed key, an uninstalled plugin, or a value of the wrong
type all produced ``False``/``None`` and a feature that simply stopped working,
with nothing in the log to say so.

This module gives those keys one home. The **literals are unchanged**: they are
a cross-process contract, and renaming them would break every installed plugin
in the one way that cannot be noticed. What changes is the shape of the read:

* one place defines each key;
* each reader states the type it expects and degrades to a default instead of
  raising when a plugin writes something else;
* an event without ``get_extra``/``set_extra`` (a duck-typed test double) reads
  as "unset" rather than crashing the pipeline.

Plugins keep writing ``set_extra("_enhance_xxx", ...)`` exactly as before; the
constants are exported so new code can import them instead of repeating strings.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "ACTIVE_REPLY_TOKEN",
    "ACTIVE_REPLY_TRIGGERED",
    "FOLLOWUP_DIRECT",
    "FOLLOWUP_TASK",
    "OWNED_IMAGE_URLS",
    "OWNED_QUOTE_IMAGE_URLS",
    "PROACTIVE_LIGHTWEIGHT",
    "VISUAL_REQUESTED",
    "VISUAL_UNAVAILABLE",
    "active_reply_token",
    "active_reply_triggered",
    "followup_direct",
    "followup_task",
    "is_active_reply",
    "owned_image_urls",
    "owned_quote_image_urls",
    "proactive_lightweight",
    "set_visual_unavailable",
    "visual_requested",
    "visual_unavailable",
]

#: Token an active-reply plugin sets to claim the turn it is answering.
ACTIVE_REPLY_TOKEN = "_enhance_active_reply_token"
#: Set once that plugin has actually fired for this turn.
ACTIVE_REPLY_TRIGGERED = "_enhance_active_reply_triggered"
#: The inbound message asked for a visual description.
VISUAL_REQUESTED = "_enhance_visual_requested"
#: Written back by the core when the requested description could not be made.
VISUAL_UNAVAILABLE = "_enhance_visual_unavailable"
#: Image references the plugin already owns, so the turn does not re-fetch them.
OWNED_IMAGE_URLS = "_enhance_owned_image_urls"
#: The same, per quoted message id.
OWNED_QUOTE_IMAGE_URLS = "_enhance_owned_quote_image_urls"
#: This turn is a follow-up the plugin is driving directly.
FOLLOWUP_DIRECT = "_enhance_followup_direct"
#: The original task text of that follow-up.
FOLLOWUP_TASK = "_enhance_followup_task"
#: The turn was started by a lightweight proactive decision.
PROACTIVE_LIGHTWEIGHT = "_enhance_proactive_lightweight"


def _read(event: Any, key: str) -> Any:
    """Return a raw extra value, or ``None`` when it cannot be read.

    Args:
        event: The message event, or any object with ``get_extra``.
        key: Extra name.

    Returns:
        The stored value, or ``None`` when the event has no reader or the reader
        raises. Callers turn ``None`` into their own default.
    """
    getter = getattr(event, "get_extra", None)
    if not callable(getter):
        return None
    try:
        return getter(key)
    except Exception:  # noqa: BLE001 - an event contract is duck-typed
        return None


def _as_text(value: Any) -> str:
    """Coerce an extra to text, treating every non-string as unset."""
    return value if isinstance(value, str) else ""


def _as_flag(value: Any) -> bool:
    """Coerce an extra to a flag.

    Only a real ``True`` counts. A plugin that writes ``1`` or ``"yes"`` means
    it too, but guessing would make the core silently disagree with plugins that
    use the value as a plain boolean; the strict reading is the one the
    surrounding conditions already rely on.
    """
    return value is True


def active_reply_token(event: Any) -> str:
    """Return the active-reply token, or ``""`` when the turn has none."""
    return _as_text(_read(event, ACTIVE_REPLY_TOKEN))


def is_active_reply(event: Any) -> bool:
    """Report whether an active-reply plugin has claimed this turn."""
    return bool(active_reply_token(event))


def active_reply_triggered(event: Any) -> bool:
    """Report whether the active-reply plugin actually fired for this turn."""
    return _as_flag(_read(event, ACTIVE_REPLY_TRIGGERED))


def visual_requested(event: Any) -> bool:
    """Report whether the inbound message asked for a visual description."""
    return _as_flag(_read(event, VISUAL_REQUESTED))


def visual_unavailable(event: Any) -> bool:
    """Report whether a requested description turned out to be unavailable."""
    return _as_flag(_read(event, VISUAL_UNAVAILABLE))


def set_visual_unavailable(event: Any, flag: bool) -> None:
    """Record that the requested description could not be produced.

    Args:
        event: The message event.
        flag: The value to store.

    Notes:
        The only extra the core writes in this group: the decision is made while
        resolving images, and a later stage reads it back.
    """
    setter = getattr(event, "set_extra", None)
    if not callable(setter):
        return
    try:
        setter(VISUAL_UNAVAILABLE, flag)
    except Exception:  # noqa: BLE001 - never break the pipeline over a marker
        return


def owned_image_urls(event: Any) -> list[str]:
    """Return the image references the plugin already owns for this turn."""
    value = _read(event, OWNED_IMAGE_URLS)
    if isinstance(value, str):
        # A bare string is the common shape of a one-image plugin; treating it
        # as a character sequence would turn a URL into a hundred of them.
        return [value] if value else []
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, str) and item]


def owned_quote_image_urls(event: Any) -> dict[str, list[str]]:
    """Return owned image references keyed by quoted message id.

    Returns:
        A mapping of message id to URLs. Entries that are not string lists are
        dropped rather than handed to a caller that will call ``.values()``.
    """
    value = _read(event, OWNED_QUOTE_IMAGE_URLS)
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, list[str]] = {}
    for message_id, urls in value.items():
        if isinstance(urls, str):
            cleaned[str(message_id)] = [urls] if urls else []
        elif isinstance(urls, (list, tuple)):
            kept = [item for item in urls if isinstance(item, str) and item]
            if kept:
                cleaned[str(message_id)] = kept
    return cleaned


def followup_direct(event: Any) -> bool:
    """Report whether this turn is a follow-up the plugin is driving."""
    return _as_flag(_read(event, FOLLOWUP_DIRECT))


def followup_task(event: Any) -> str:
    """Return the original task text of a direct follow-up, or ``""``."""
    return _as_text(_read(event, FOLLOWUP_TASK))


def proactive_lightweight(event: Any) -> bool:
    """Report whether the turn came from a lightweight proactive decision."""
    return _as_flag(_read(event, PROACTIVE_LIGHTWEIGHT))
