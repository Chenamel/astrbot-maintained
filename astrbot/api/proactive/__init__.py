"""Proactive capability flags for plugins.

Public surface (see ``docs/maintained/api-contract.md``):

- :func:`available`
- :func:`proactive_switch_is_disabled`
- :func:`is_lightweight_proactive`

The maintained fork keeps the proactive-reply switch disabled at all times.
This module therefore exposes no way to enable it: it only reports the
invariant and lets a plugin ask whether the core has classified a request as a
lightweight proactive scenario.
"""

from __future__ import annotations

from typing import Any

from astrbot.api._bridge import resolve

__all__ = [
    "available",
    "is_lightweight_proactive",
    "proactive_switch_is_disabled",
]

_MODULE = "astrbot.core.astr_main_agent"


def proactive_switch_is_disabled() -> bool:
    """Return whether proactive replies are guaranteed to stay disabled.

    Always ``True``. The invariant is recorded in
    ``maintained/installed_manifest.json`` as ``proactive_must_remain_disabled``
    and no code path may enable proactive replies.

    Returns:
        ``True``, unconditionally.
    """
    return True


def is_lightweight_proactive(event: Any) -> bool:
    """Return whether the core classified this request as lightweight proactive.

    Fails closed: when the classifier is unavailable the request is treated as
    a normal request so that it takes the full, well-tested path.

    Args:
        event: The event to inspect.

    Returns:
        ``True`` only when the core explicitly classified the request.
    """
    classifier = resolve(_MODULE, "_is_lightweight_proactive_request", None)
    if classifier is None:
        return False
    try:
        return bool(classifier(event))
    except Exception:  # noqa: BLE001 - never route into a narrow path on error
        return False


def available() -> bool:
    """Return whether the core-side proactive classifier is installed."""
    return resolve(_MODULE, "_is_lightweight_proactive_request", None) is not None
