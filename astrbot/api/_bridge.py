"""Internal capability bridge for the maintained fork's additive API modules.

This module is **not** part of the public API surface. External consumers
(plugins) must import from the documented submodules -- ``astrbot.api.media``,
``astrbot.api.turns``, ``astrbot.api.delivery``, ``astrbot.api.permissions``,
``astrbot.api.proactive`` -- and never from here.

The additional API modules forward to core-side implementations that may be
absent. That happens, for example, when upstream overwrote the maintained
patches, or before those patches are re-applied. :func:`resolve` keeps the
public modules importable and callable in that situation by returning a safe
default instead of raising.

See ``docs/maintained/api-contract.md`` for the documented degradation rules.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

logger = logging.getLogger("astrbot")

__all__: list[str] = []

_MISSING = object()

# Only successful lookups are cached: a capability that appears later in the
# same process (for example after a plugin reload) must still be discovered.
_CACHE: dict[tuple[str, str], Any] = {}
_REPORTED: set[tuple[str, str]] = set()

#: Capability name -> (module path, attribute name) of the core-side provider.
CAPABILITIES: dict[str, tuple[str, str]] = {
    "turns.direct_turn": (
        "astrbot.core.utils.direct_turns",
        "coordinator",
    ),
    "delivery.code_policy": (
        "astrbot.core.code_delivery_policy",
        "code_task_spec",
    ),
    "permissions.execution_policy": (
        "astrbot.core.code_delivery_policy",
        "execution_denial",
    ),
    "proactive.lightweight": (
        "astrbot.core.astr_main_agent",
        "_is_lightweight_proactive_request",
    ),
    "media.unavailable_contract": (
        "astrbot.core.provider.entities",
        "IMAGE_INPUT_UNAVAILABLE_NOTICE",
    ),
}


def resolve(module: str, name: str, default: Any = None) -> Any:
    """Resolve an attribute from an optional core module.

    Args:
        module: Dotted module path, e.g. ``astrbot.core.utils.direct_turns``.
        name: Attribute name to look up.
        default: Value returned when the module or attribute is unavailable.

    Returns:
        The resolved attribute, or ``default`` when the module cannot be
        imported or does not define ``name``. Unavailability is logged once
        per ``(module, name)`` pair to keep logs readable.
    """
    key = (module, name)
    if key in _CACHE:
        return _CACHE[key]

    value: Any = _MISSING
    try:
        value = getattr(importlib.import_module(module), name, _MISSING)
    except Exception:  # noqa: BLE001 - an optional patch must never break import
        value = _MISSING

    if value is _MISSING:
        if key not in _REPORTED:
            _REPORTED.add(key)
            logger.info(
                "Maintained API capability unavailable: %s.%s; safe default in use.",
                module,
                name,
            )
        return default

    _CACHE[key] = value
    return value


def capabilities() -> dict[str, bool]:
    """Report which core-side capabilities are currently available.

    Returns:
        A mapping of capability name to availability, sorted by name. Intended
        for diagnostics and for callers that want to adapt before calling.
    """
    report: dict[str, bool] = {}
    for feature, (module, name) in sorted(CAPABILITIES.items()):
        try:
            getattr(importlib.import_module(module), name)
        except Exception:  # noqa: BLE001 - absence is a valid, expected state
            report[feature] = False
        else:
            report[feature] = True
    return report
