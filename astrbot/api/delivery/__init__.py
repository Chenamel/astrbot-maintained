"""Delivery policy helpers for plugins.

Exposes the code-delivery checks the core uses to decide whether a model
actually delivered source code, and the fallback text used when it did not.

Public surface (see ``docs/maintained/api-contract.md``):

- :data:`CODE_DELIVERY_FAILURE`
- :func:`available`
- :func:`code_task_spec`
- :func:`has_code_delivery`

When the core-side policy is absent the helpers return conservative defaults
(``None`` / ``False``) rather than guessing.
"""

from __future__ import annotations

from typing import Any

from astrbot.api._bridge import resolve

__all__ = [
    "CODE_DELIVERY_FAILURE",
    "available",
    "code_task_spec",
    "has_code_delivery",
]

_MODULE = "astrbot.core.code_delivery_policy"

#: Text returned when a code task could not be repaired into a real delivery.
CODE_DELIVERY_FAILURE: str = resolve(
    _MODULE,
    "CODE_DELIVERY_FAILURE",
    "这次没生成完整代码，可以再试一次",
)


def available() -> bool:
    """Return whether the core-side delivery policy is installed."""
    return resolve(_MODULE, "code_task_spec", None) is not None


def code_task_spec(event: Any) -> tuple[str, str] | None:
    """Describe the code task carried by an event, if any.

    Args:
        event: The event to inspect.

    Returns:
        A ``(text, language)`` pair when the event asks for code, otherwise
        ``None``.
    """
    resolver = resolve(_MODULE, "code_task_spec", None)
    if resolver is None:
        return None
    try:
        spec = resolver(event)
    except Exception:  # noqa: BLE001 - policy absence must not raise to callers
        return None
    if isinstance(spec, (tuple, list)) and len(spec) == 2:
        return str(spec[0]), str(spec[1])
    return None


def has_code_delivery(text: str, language: str = "") -> bool:
    """Return whether a model reply actually delivers source code.

    Args:
        text: The model reply text.
        language: Expected language hint; empty means "infer".

    Returns:
        ``True`` when the reply contains a real, non-elided code block.
    """
    checker = resolve(_MODULE, "has_code_delivery", None)
    if checker is None:
        return False
    try:
        return bool(checker(text, language))
    except Exception:  # noqa: BLE001 - treat an unusable policy as "no delivery"
        return False
