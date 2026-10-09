"""Runtime helpers that plugins commonly need.

Public surface (see ``docs/maintained/api-contract.md``):

- :func:`available`
- :func:`get_astrbot_data_path`
- :func:`download_image_by_url`
- :func:`extract_quoted_message_images`

Degradation is explicit rather than silent:

- paths fall back to ``<cwd>/data``;
- quoting falls back to "no images found" (an empty list);
- downloading fails loudly, because silently returning no image would corrupt
  the caller's context instead of surfacing the problem.
"""

from __future__ import annotations

import pathlib
from typing import Any

from astrbot.api._bridge import resolve

__all__ = [
    "available",
    "download_image_by_url",
    "extract_quoted_message_images",
    "get_astrbot_data_path",
]

_PATH_MODULE = "astrbot.core.utils.astrbot_path"
_IO_MODULE = "astrbot.core.utils.io"
_QUOTE_MODULE = "astrbot.core.utils.quoted_message_parser"


def available() -> bool:
    """Return whether the core-side runtime helpers are installed."""
    return resolve(_PATH_MODULE, "get_astrbot_data_path", None) is not None


def get_astrbot_data_path() -> str:
    """Return the AstrBot data directory.

    Falls back to ``<cwd>/data`` when the core helper is unavailable, which
    keeps plugins loadable on an unpatched core.

    Returns:
        An absolute path string.
    """
    helper = resolve(_PATH_MODULE, "get_astrbot_data_path", None)
    if helper is not None:
        try:
            return str(helper())
        except Exception:  # noqa: BLE001 - fall through to the literal default
            pass
    return str(pathlib.Path.cwd() / "data")


async def download_image_by_url(url: str, *args: Any, **kwargs: Any) -> Any:
    """Download an image through the core helper.

    Args:
        url: Image URL to download.
        *args: Forwarded to the core helper.
        **kwargs: Forwarded to the core helper.

    Returns:
        Whatever the core helper returns (typically a local file path).

    Raises:
        RuntimeError: When the core helper is unavailable. Failing loudly is
            deliberate: a silently missing image would corrupt the caller's
            visual context.
    """
    helper = resolve(_IO_MODULE, "download_image_by_url", None)
    if helper is None:
        raise RuntimeError(
            "download_image_by_url is unavailable: the core helper is missing."
        )
    return await helper(url, *args, **kwargs)


async def extract_quoted_message_images(event: Any, component: Any) -> list[Any]:
    """Extract images referenced by a quoted message.

    Args:
        event: The message event carrying the quote.
        component: The quote component to inspect.

    Returns:
        The list of image references, or an empty list when the core helper is
        unavailable (degrading to "the quote had no images").
    """
    helper = resolve(_QUOTE_MODULE, "extract_quoted_message_images", None)
    if helper is None:
        return []
    result = await helper(event, component)
    return list(result) if result else []
