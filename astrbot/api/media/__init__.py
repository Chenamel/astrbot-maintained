"""Media input contract shared by the core and plugins.

Exposes the image-input contract that the core publishes when the maintained
patches are installed, and keeps the same values available when they are not.
This is what lets a plugin import the contract at module level without turning
a core-side version drift into a plugin startup failure.

Public surface (see ``docs/maintained/api-contract.md``):

- :data:`IMAGE_CAPTION_MARKER`
- :data:`IMAGE_INPUT_UNAVAILABLE_MESSAGE`
- :data:`IMAGE_INPUT_UNAVAILABLE_NOTICE`
- :func:`has_visual_input`
- :func:`has_image_caption`
- :func:`image_input_available`
- :func:`available`
"""

from __future__ import annotations

from typing import Any

from astrbot.api._bridge import resolve

__all__ = [
    "IMAGE_CAPTION_MARKER",
    "IMAGE_INPUT_UNAVAILABLE_MESSAGE",
    "IMAGE_INPUT_UNAVAILABLE_NOTICE",
    "available",
    "has_image_caption",
    "has_visual_input",
    "image_input_available",
]

#: Marker wrapped around a generated image description inside request content.
IMAGE_CAPTION_MARKER = "<image_caption>"

#: Text shown to the user when the current image has no usable visual evidence.
IMAGE_INPUT_UNAVAILABLE_MESSAGE: str = resolve(
    "astrbot.core.provider.entities",
    "IMAGE_INPUT_UNAVAILABLE_MESSAGE",
    "当前看不到图片，请重新发送。",
)

#: Instruction injected for the model when the current image has no usable
#: visual evidence. The core publishes the same text; this mirror is used only
#: when the core-side constant is unavailable.
IMAGE_INPUT_UNAVAILABLE_NOTICE: str = resolve(
    "astrbot.core.provider.entities",
    "IMAGE_INPUT_UNAVAILABLE_NOTICE",
    "[Image unavailable: no visual evidence was received. "
    "Do not infer or describe the image from history, filenames or "
    f"surrounding text. Reply only: {IMAGE_INPUT_UNAVAILABLE_MESSAGE}]",
)


def _part_text(part: Any) -> str:
    """Return the text carried by a content part, if any."""
    if isinstance(part, str):
        return part
    if isinstance(part, dict):
        text = part.get("text")
        return text if isinstance(text, str) else ""
    text = getattr(part, "text", None)
    return text if isinstance(text, str) else ""


def _is_image_part(part: Any) -> bool:
    """Return whether a content part carries an image reference."""
    if isinstance(part, dict):
        return part.get("type") == "image_url"
    image_url_part = resolve("astrbot.core.agent.message", "ImageURLPart", None)
    if image_url_part is not None:
        return isinstance(part, image_url_part)
    return type(part).__name__ == "ImageURLPart"


def has_visual_input(request: Any) -> bool:
    """Return whether a provider request carries real visual evidence.

    Args:
        request: A ``ProviderRequest``-like object.

    Returns:
        ``True`` when the request has image URLs or an image content part.
    """
    if request is None:
        return False
    if getattr(request, "image_urls", None):
        return True
    parts = getattr(request, "extra_user_content_parts", None) or ()
    return any(_is_image_part(part) for part in parts)


def has_image_caption(parts: Any) -> bool:
    """Return whether any content part carries an image caption.

    Args:
        parts: An iterable of content parts (objects or OpenAI-style dicts).

    Returns:
        ``True`` when at least one part contains :data:`IMAGE_CAPTION_MARKER`.
    """
    if not parts:
        return False
    return any(IMAGE_CAPTION_MARKER in _part_text(part) for part in parts)


def image_input_available(request: Any) -> bool:
    """Return whether visual input is usable for this request.

    Prefers the flag maintained by the core. When the flag is absent the
    decision falls back to whether the request carries visual input at all.

    Args:
        request: A ``ProviderRequest``-like object.

    Returns:
        ``True`` when the model can rely on visual evidence.
    """
    if request is None:
        return False
    flagged = getattr(request, "image_input_unavailable", None)
    if isinstance(flagged, bool):
        return not flagged
    return has_visual_input(request)


def available() -> bool:
    """Return whether the core-side media contract is installed."""
    return (
        resolve(
            "astrbot.core.provider.entities",
            "IMAGE_INPUT_UNAVAILABLE_NOTICE",
            None,
        )
        is not None
    )
