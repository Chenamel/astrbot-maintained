"""Proactive capability flags for plugins.

Public surface (see ``docs/maintained/api-contract.md``):

- :func:`available`
- :func:`proactive_switch_is_disabled`
- :func:`is_lightweight_proactive`
- :func:`generate_with_persona`

This layer keeps the default-off policy and deliberately exposes no way to
trigger a proactive reply: it reports that fact, lets a plugin ask whether the
core has classified a request as a lightweight proactive scenario, and lets a
plugin generate wording that goes through the persona chain.

This is a division of responsibility, not a global restriction. Upstream's
built-in ``provider_ltm_settings.active_reply.enable`` (off by default) and a
plugin's own switch are independent of this module. Enabling both on the same
instance would send two proactive replies for one message.
"""

from __future__ import annotations

import json
from typing import Any

from astrbot.api._bridge import resolve
from astrbot.core import logger

__all__ = [
    "available",
    "generate_with_persona",
    "is_lightweight_proactive",
    "persona_available",
    "proactive_switch_is_disabled",
    "record_bot_message",
    "record_user_message",
]

_MODULE = "astrbot.core.astr_main_agent"
_PERSONA_MODULE = "astrbot.core.proactive_persona"


def proactive_switch_is_disabled() -> bool:
    """Report that this API layer does not trigger proactive replies.

    Always ``True``. The default-off policy is recorded in
    ``maintained/installed_manifest.json`` as ``proactive_must_remain_disabled``.
    This says nothing about the rest of the bot: upstream's built-in
    ``active_reply.enable`` setting and a plugin's own switch are independent.

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


async def record_bot_message(context: Any, event: Any, text: str) -> bool:
    """Record a message the bot just sent into the platform history.

    Args:
        context: Unused for now; kept so this matches its sibling helpers.
        event: The event whose conversation the message belongs to.
        text: What the bot sent, already stripped of control tags.

    Returns:
        True when the row was written, False when recording was skipped.

    Notes:
        History is what later turns reason over. A bot that reads the group's
        lines but not its own replies loses track of what it already said, so a
        proactive reply has to be written back the same way an answered message
        is. ``sender_id`` is the literal ``"bot"`` -- the history readers
        already key on it to tell our own lines apart.
    """
    del context
    if not text:
        return False
    try:
        from astrbot.core import db_helper
    except Exception:  # noqa: BLE001 - recording is best effort
        return False

    platform_id = ""
    getter = getattr(event, "get_platform_id", None)
    if callable(getter):
        platform_id = getter() or ""
    umo = getattr(event, "unified_msg_origin", "") or ""
    if not platform_id or not umo:
        return False

    # Same key the history reader computes, or the row would be written under
    # one conversation and looked up under another.
    _, _, tail = umo.partition(":")
    user_id = f"{platform_id}:{tail}" if tail else umo
    try:
        await db_helper.insert_platform_message_history(
            platform_id=platform_id,
            user_id=user_id,
            content={"type": "bot", "message": [{"type": "plain", "text": text}]},
            sender_id="bot",
            sender_name="bot",
        )
        return True
    except Exception as exc:  # noqa: BLE001 - a failed record must not break the send
        logger.warning("record_bot_message failed: %s", exc)
        return False


async def record_user_message(
    context: Any, event: Any, text: str, max_messages: int = 700
) -> bool:
    """Record an incoming group message into the platform history.

    Args:
        context: Unused for now; kept so this matches its sibling helpers.
        event: The event being recorded.
        text: The message text, already cleaned.
        max_messages: Rows kept per conversation before the oldest are dropped.

    Returns:
        True when the conversation now holds this line -- either because we
        wrote it or because core had already recorded it. False means nothing
        landed and the caller is right to worry.

    Notes:
        The return value answers "is it in history now", not "did I write it".
        Core records group history too, from a handler with the *lowest*
        priority, so any plugin that stops the event earlier skips it -- and a
        judgement then reasons over a history that stopped hours ago. Writing
        from the plugin side keeps the record complete regardless of what other
        plugins do to the event. Reporting the resulting duplicate as a failure
        buried real write errors under thousands of bogus warnings, so hitting
        the duplicate check is reported the same as writing the row.
    """
    del context
    if not text:
        return False
    try:
        from astrbot.core import db_helper
    except Exception:  # noqa: BLE001 - recording is best effort
        return False

    platform_id = ""
    getter = getattr(event, "get_platform_id", None)
    if callable(getter):
        platform_id = getter() or ""
    umo = getattr(event, "unified_msg_origin", "") or ""
    if not platform_id or not umo:
        return False

    _, _, tail = umo.partition(":")
    user_id = f"{platform_id}:{tail}" if tail else umo
    sender_id = ""
    sender_getter = getattr(event, "get_sender_id", None)
    if callable(sender_getter):
        sender_id = sender_getter() or ""
    sender_name = ""
    name_getter = getattr(event, "get_sender_name", None)
    if callable(name_getter):
        sender_name = name_getter() or ""
    # Core writes group history too, but only when no plugin stopped the event
    # first, so it races us. Checking the last few rows costs one indexed read
    # and keeps a single copy -- writing twice would halve how much history fits
    # in the retention window.
    try:
        recent = await db_helper.get_platform_message_history(
            platform_id=platform_id,
            user_id=user_id,
            page=1,
            page_size=4,
        )
        wanted = text[:40]
        for row in recent or []:
            if str(getattr(row, "sender_id", "") or "") != (sender_id or ""):
                continue
            # content is JSON with escaped characters, so compare the decoded
            # text -- a plain substring test would never match Chinese.
            raw = getattr(row, "content", "")
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except ValueError:
                    continue
            parts = raw.get("message") if isinstance(raw, dict) else None
            if not isinstance(parts, list):
                continue
            stored = "".join(
                str(part.get("text", ""))
                for part in parts
                if isinstance(part, dict) and part.get("type") == "plain"
            )
            if stored[:40] == wanted:
                logger.debug(
                    "record_user_message: core already recorded %r", wanted[:20]
                )
                return True
    except Exception:  # noqa: BLE001 - dedup is an optimisation, not a gate
        pass

    try:
        await db_helper.insert_platform_message_history(
            platform_id=platform_id,
            user_id=user_id,
            content={"type": "user", "message": [{"type": "plain", "text": text}]},
            sender_id=sender_id or None,
            sender_name=sender_name or None,
            max_messages=max_messages,
        )
        return True
    except Exception as exc:  # noqa: BLE001 - a failed record must not break flow
        logger.warning("record_user_message failed: %s", exc)
        return False
