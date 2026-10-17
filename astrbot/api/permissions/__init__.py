"""Permission and execution-authorization helpers for plugins.

Public surface (see ``docs/maintained/api-contract.md``):

- :func:`available`
- :func:`is_admin`
- :func:`execution_denial`

Security semantics: :func:`execution_denial` never degrades to "allow". When
the core-side policy engine is missing it falls back to the administrator-only
check, which is the strength the upstream core already enforced. Returning
``None`` means "no objection from this layer" -- it does **not** grant
authorization, so callers must still apply their own guard.
"""

from __future__ import annotations

from typing import Any

from astrbot.api._bridge import resolve

__all__ = [
    "EXECUTION_NOT_AUTHORIZED",
    "available",
    "execution_denial",
    "is_admin",
]

_MODULE = "astrbot.core.code_delivery_policy"

#: Reason returned when no layer could authorize an execution-style operation.
EXECUTION_NOT_AUTHORIZED = (
    "Execution is not authorized for this request. "
    "An administrator must explicitly ask to run it."
)

#: Reason returned when the policy engine is present but failed to decide.
#: Deliberately module-private: it is an internal fail-closed fallback and must
#: not become part of the versioned public surface (see api-contract.md §3.4).
_EXECUTION_POLICY_UNAVAILABLE = (
    "Execution authorization could not be verified; the operation was blocked."
)


def _sender_id(event: Any) -> str:
    """Return the sender identifier of an event, if available."""
    getter = getattr(event, "get_sender_id", None)
    if callable(getter):
        try:
            value = getter()
        except Exception:  # noqa: BLE001 - event contract is duck-typed
            value = None
        if value is not None and str(value):
            return str(value)
    sender = getattr(getattr(event, "message_obj", None), "sender", None)
    value = getattr(sender, "user_id", None)
    return "" if value is None else str(value)


def _admin_ids(config: Any) -> set[str]:
    """Return the configured administrator identifiers as strings."""
    if config is None:
        return set()
    try:
        raw = config.get("admins_id")
    except Exception:  # noqa: BLE001 - config objects vary across versions
        return set()
    if raw is None:
        return set()
    if isinstance(raw, str):
        raw = [raw]
    try:
        return {str(item) for item in raw}
    except TypeError:
        return {str(raw)}


def is_admin(event: Any, config: Any) -> bool:
    """Return whether the sender is a configured administrator.

    Args:
        event: The event to inspect.
        config: The AstrBot config mapping containing ``admins_id``.

    Returns:
        ``True`` when the sender is listed as an administrator.
    """
    sender = _sender_id(event)
    if not sender:
        return False
    return sender in _admin_ids(config)


def execution_denial(event: Any, config: Any) -> str | None:
    """Decide whether an execution-style operation must be refused.

    Args:
        event: The event that triggered the operation.
        config: The AstrBot config mapping.

    Returns:
        A human-readable reason when the operation must be refused, otherwise
        ``None``.
    """
    provider_settings = (
        config.get("provider_settings", {}) if isinstance(config, dict) else {}
    )
    if provider_settings.get("execution_gate_mode", "legacy") == "legacy":
        # Upstream-compatible default: the administrator check alone decides.
        return None if is_admin(event, config) else EXECUTION_NOT_AUTHORIZED
    decider = resolve(_MODULE, "execution_denial", None)
    if decider is not None:
        try:
            reason = decider(event, config)
        except Exception:  # noqa: BLE001 - fail closed on an unusable policy
            return _EXECUTION_POLICY_UNAVAILABLE
        if isinstance(reason, str) and reason.strip():
            return reason
        return None
    if is_admin(event, config):
        return None
    return EXECUTION_NOT_AUTHORIZED


def available() -> bool:
    """Return whether the core-side execution policy is installed."""
    return resolve(_MODULE, "execution_denial", None) is not None
