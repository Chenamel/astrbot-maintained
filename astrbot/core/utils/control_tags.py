"""Strip leftover control tags from outgoing plain text.

Several plugins (and the model itself) express control actions with inline
tags such as ``<quote id="..."/>`` or ``<mention id="123"/>``; each plugin is
supposed to parse them on the way back. When one fails to -- a different hook
order, a code block, an intermediate tool-loop turn -- the tag reaches the
group as literal text, which looks broken to everyone reading.

This is the last line of defence: it removes those tags right before a message
chain leaves the process, and logs when it had to, so the source can still be
tracked down.

Only *known control tags* are stripped. A generic ``<foo bar="baz"/>`` pattern
is deliberately not used: it would mangle code snippets users legitimately
paste.
"""

from __future__ import annotations

import re

CONTROL_TAG_RE = re.compile(
    r"</?(?:quote|mention|refuse|at)\b[^>]*/?>",
    re.IGNORECASE,
)
"""Tags that never belong in a chat message as literal text."""


def strip_control_tags(chain: list) -> int:
    """Remove control tags from the plain-text parts of a message chain.

    Args:
        chain: Message chain components; plain components are edited in place.

    Returns:
        How many components were changed (0 means the chain was clean).
    """
    changed = 0
    for comp in chain:
        text = getattr(comp, "text", None)
        if not isinstance(text, str) or not text:
            continue
        cleaned = CONTROL_TAG_RE.sub("", text)
        if cleaned == text:
            continue
        # Collapse the leading whitespace a removed tag usually leaves behind.
        comp.text = cleaned.lstrip() if cleaned.lstrip() else cleaned
        changed += 1
    return changed
