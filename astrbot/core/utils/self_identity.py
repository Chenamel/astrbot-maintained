"""One statement of the self-identity invariant.

The prompt tells the model who the current sender is, but never which account
is its own. A transcript full of other people's words then invites it to
attribute a line to itself -- which is what happened on 2026-11-02 11:58, when
a proactive reply called somebody else's line "my own receipt".

The text lives here and only here: the normal reply path and the proactive
persona path both inject it, and two copies would drift silently.
"""

from __future__ import annotations

from typing import Any

from astrbot.core.platform.message_type import MessageType


def self_identity_note(event: Any) -> str:
    """Return the identity sentence for this event, or "" without a self id.

    Args:
        event: The message event. Only ``get_self_id`` and
            ``get_message_type`` are used, so test doubles work unchanged.

    Returns:
        A one-paragraph note. Empty when the platform did not report a self id:
        naming an account we cannot verify would be worse than saying nothing.
    """
    try:
        raw = event.get_self_id()
    except Exception:  # noqa: BLE001 - duck-typed events
        return ""
    # Only a real id may be written into the prompt. A mock or an object with a
    # custom __str__ would otherwise put "<MagicMock ...>" in front of the model,
    # which is worse than saying nothing.
    if isinstance(raw, bool) or not isinstance(raw, (str, int)):
        return ""
    self_id = str(raw).strip()
    if not self_id:
        return ""

    note = f"Your account: {self_id}."
    try:
        is_group = event.get_message_type() == MessageType.GROUP_MESSAGE
    except Exception:  # noqa: BLE001 - duck-typed events
        is_group = False
    if is_group:
        note += (
            " In the group transcript, only lines marked BOT, 机器人 or [You] are"
            " your own words; a line under another nickname belongs to that"
            " member. If you cannot find a line in your own record, do not claim"
            " you said it."
        )
    return note
