"""Message content parts shared by the core and plugins.

Public surface (see ``docs/maintained/api-contract.md``):

- :data:`TextPart`
- :data:`ImageURLPart`
- :func:`available`
- :func:`is_text_part`
- :func:`is_image_part`

When the core does not provide these types the attributes are ``None`` and the
``is_*`` helpers return ``False``, so importing this module never fails. Callers
must use the helpers for type checks -- ``isinstance(x, None)`` would raise.
"""

from __future__ import annotations

from typing import Any

from astrbot.api._bridge import resolve

__all__ = [
    "ImageURLPart",
    "TextPart",
    "available",
    "is_image_part",
    "is_text_part",
]

_MODULE = "astrbot.core.agent.message"

#: Text content part type, or ``None`` when the core does not provide it.
TextPart: Any = resolve(_MODULE, "TextPart", None)

#: Image URL content part type, or ``None`` when the core does not provide it.
ImageURLPart: Any = resolve(_MODULE, "ImageURLPart", None)


def available() -> bool:
    """Return whether the core-side content part types are installed."""
    return TextPart is not None


def is_text_part(part: Any) -> bool:
    """Return whether ``part`` is a text content part.

    Args:
        part: A content part object or OpenAI-style dict.

    Returns:
        ``True`` only when the core type is available and ``part`` is one.
    """
    return TextPart is not None and isinstance(part, TextPart)


def is_image_part(part: Any) -> bool:
    """Return whether ``part`` carries an image reference.

    Accepts both the core content part type and the OpenAI-style
    ``{"type": "image_url"}`` mapping, so callers do not need to know which
    form a request happens to use.

    Args:
        part: A content part object or OpenAI-style dict.

    Returns:
        ``True`` when ``part`` references an image.
    """
    if ImageURLPart is not None and isinstance(part, ImageURLPart):
        return True
    if isinstance(part, dict):
        return part.get("type") == "image_url"
    return False
