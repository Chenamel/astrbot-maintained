"""Runtime helpers that plugins commonly need.

Public surface (see ``docs/maintained/api-contract.md``):

- :func:`available`
- :func:`get_astrbot_data_path`
- :func:`download_image_by_url`
- :func:`extract_quoted_message_images`
- :data:`HOOK_TIMING_ENHANCED` / :data:`HOOK_TIMING_LEGACY` / :func:`hook_timing_mode`

Degradation is explicit rather than silent:

- paths fall back to ``<cwd>/data``;
- quoting falls back to "no images found" (an empty list);
- downloading fails loudly, because silently returning no image would corrupt
  the caller's context instead of surfacing the problem;
- the hook timing query falls back to ``"enhanced"``, which is this fork's
  default, so plugins can always compare against a known value.
"""

from __future__ import annotations

import pathlib
from typing import Any

from astrbot.api._bridge import resolve

__all__ = [
    "HOOK_TIMING_ENHANCED",
    "HOOK_TIMING_LEGACY",
    "available",
    "download_image_by_url",
    "extract_quoted_message_images",
    "get_astrbot_data_path",
    "hook_timing_mode",
]

_PATH_MODULE = "astrbot.core.utils.astrbot_path"
_IO_MODULE = "astrbot.core.utils.io"
_QUOTE_MODULE = "astrbot.core.utils.quoted_message_parser"
_HOOK_TIMING_MODULE = "astrbot.core.config.agent_runner"

#: Hook timing mode in which the agent-completion hook fires **before** the reply
#: is emitted, so audit and rewrite plugins get control first. This is this
#: fork's default and the value returned when the core side is unavailable.
HOOK_TIMING_ENHANCED: str = resolve(
    _HOOK_TIMING_MODULE, "HOOK_TIMING_MODE_ENHANCED", "enhanced"
)

#: Hook timing mode that restores the upstream timing ("reply first, completion
#: hook after") on every code path that has an upstream counterpart.
HOOK_TIMING_LEGACY: str = resolve(
    _HOOK_TIMING_MODULE, "HOOK_TIMING_MODE_LEGACY", "legacy"
)


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


def hook_timing_mode() -> str:
    """Return the agent-completion hook timing mode currently in effect.

    ``"enhanced"`` means the completion hook fires **before** the reply is
    emitted; ``"legacy"`` means the upstream timing is restored on every code
    path that has an upstream counterpart. Plugins that depend on "the reply has
    already been sent" should check this and take their conservative path or
    tell the user when the mode is ``"legacy"``.

    Returns:
        ``"enhanced"`` or ``"legacy"``. Falls back to :data:`HOOK_TIMING_LEGACY`
        when the core helper is unavailable, raises, or reports an unknown value.
    """
    helper = resolve(_HOOK_TIMING_MODULE, "hook_timing_mode", None)
    if helper is None:
        return str(HOOK_TIMING_LEGACY)
    try:
        mode = helper()
    except Exception:  # noqa: BLE001 - fall through to the fork default
        return str(HOOK_TIMING_LEGACY)
    if mode in (HOOK_TIMING_ENHANCED, HOOK_TIMING_LEGACY):
        return str(mode)
    return str(HOOK_TIMING_LEGACY)


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
