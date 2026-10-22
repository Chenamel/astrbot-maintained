"""Proactive capability flags for plugins.

Public surface (see ``docs/maintained/api-contract.md``):

- :func:`available`
- :func:`proactive_switch_is_disabled`
- :func:`is_lightweight_proactive`
- :func:`generate_with_persona`

The maintained fork keeps the proactive-reply switch disabled at all times.
This module therefore exposes no way to enable it: it only reports the
invariant, lets a plugin ask whether the core has classified a request as a
lightweight proactive scenario, and lets a plugin generate wording that goes
through the persona chain.
"""

from __future__ import annotations

from typing import Any

from astrbot.api._bridge import resolve

__all__ = [
    "available",
    "generate_with_persona",
    "is_lightweight_proactive",
    "persona_available",
    "proactive_switch_is_disabled",
]

_MODULE = "astrbot.core.astr_main_agent"
_PERSONA_MODULE = "astrbot.core.proactive_persona"


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


def persona_available() -> bool:
    """Return whether persona-aware generation is installed."""
    return resolve(_PERSONA_MODULE, "generate_with_persona", None) is not None


async def generate_with_persona(
    context: Any,
    event: Any,
    prompt: str,
    system_prompt: str = "",
    image_urls: list[str] | None = None,
    chat_provider_id: str | None = None,
    timeout: float | None = None,
) -> Any | None:
    """Generate wording for a proactive reply through the persona chain.

    ``Context.llm_generate`` bypasses the ``on_llm_request`` hook, so text it
    produces carries no persona and no long-term memory. This routes the
    request through that hook first, letting persona and memory plugins
    contribute exactly as they do for a normal reply.

    Args:
        context: The plugin ``Context``.
        event: The event that triggered the proactive reply.
        prompt: What the bot should react to or say.
        system_prompt: Optional extra instruction for this single call.
        image_urls: Optional images to include with the prompt.
        chat_provider_id: Provider to use; defaults to the current provider.
        timeout: Optional seconds bound for the provider call.

    Returns:
        The ``LLMResponse``, or ``None`` when the capability is missing, no
        provider is available, or a plugin cancelled the request.
    """
    generate = resolve(_PERSONA_MODULE, "generate_with_persona", None)
    if generate is None:
        return None
    return await generate(
        context,
        event,
        prompt,
        system_prompt=system_prompt,
        image_urls=image_urls,
        chat_provider_id=chat_provider_id,
        timeout=timeout,
    )
