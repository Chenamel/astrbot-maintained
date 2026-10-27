"""Persona-aware generation for plugin-driven (proactive) replies.

Plugins cannot reach the persona chain on their own. ``Context.llm_generate``
and ``Context.tool_loop_agent`` both call the provider directly and skip the
``on_llm_request`` hook, which is exactly where plugins inject persona
(self_learning), long-term memory (livingmemory) and group context
(enhance_mode). A proactive reply produced without that hook reads like a
helpdesk answer instead of like the bot that already talks in the group.

This module builds a ``ProviderRequest``, runs it through the same hook the
normal pipeline uses, and only then calls the provider. It is purely additive:
nothing runs unless a plugin asks for it, so no existing behaviour changes.
"""

from __future__ import annotations

import asyncio
from typing import Any

from astrbot import logger
from astrbot.core.pipeline.context_utils import call_event_hook
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.star_handler import EventType

__all__ = ["generate_with_persona"]


async def _resolve_provider(context: Any, chat_provider_id: str | None) -> Any | None:
    """Look up the provider to use.

    Args:
        context: The plugin ``Context`` carrying a provider manager.
        chat_provider_id: Explicit provider id, or ``None`` for the default.

    Returns:
        A provider instance, or ``None`` when none can be resolved.
    """
    manager = getattr(context, "provider_manager", None)
    if manager is None:
        return None
    if chat_provider_id:
        getter = getattr(manager, "get_provider_by_id", None)
        if getter is None:
            return None
        return await getter(chat_provider_id)
    return getattr(manager, "curr_provider_inst", None)


async def generate_with_persona(
    context: Any,
    event: Any,
    prompt: str,
    system_prompt: str = "",
    image_urls: list[str] | None = None,
    chat_provider_id: str | None = None,
    timeout: float | None = None,
) -> Any | None:
    """Generate a reply with the persona chain applied.

    Args:
        context: The plugin ``Context``.
        event: The message event that triggered this proactive reply.
        prompt: What the bot should react to or say.
        system_prompt: Optional extra instruction for this single call.
        image_urls: Optional images to include with the prompt.
        chat_provider_id: Provider to use; defaults to the current provider.
        timeout: Optional seconds bound for the provider call.

    Returns:
        The ``LLMResponse`` from the provider, or ``None`` when no provider is
        available or a plugin cancelled the request through the hook.
    """
    provider = await _resolve_provider(context, chat_provider_id)
    if provider is None:
        logger.info("proactive persona generation skipped: no provider available")
        return None

    req = ProviderRequest(
        prompt=prompt,
        system_prompt=system_prompt,
        image_urls=list(image_urls or []),
        session_id=getattr(event, "unified_msg_origin", "") or "",
    )
    # Plugins mutate req here: persona, memory, group context.
    if await call_event_hook(event, EventType.OnLLMRequestEvent, req):
        return None

    coro = provider.text_chat(
        prompt=req.prompt,
        system_prompt=req.system_prompt,
        image_urls=req.image_urls,
        contexts=req.contexts or None,
    )

    async def _with_stats():
        resp = await coro
        # Mirror the agent-runner usage stats so dashboard totals cover this
        # path too; a stats failure must never break the reply.
        try:
            from astrbot.core import db_helper

            await db_helper.insert_provider_stat(
                umo=getattr(event, "unified_msg_origin", "") or "unknown",
                conversation_id=None,
                provider_id=chat_provider_id or provider.meta().id,
                provider_model=provider.get_model(),
                status="completed" if resp.role != "err" else "error",
                # LLMResponse exposes TokenUsage as .usage; .stats does not
                # exist, so the old lookup raised and this path went unrecorded.
                stats=(
                    {
                        "token_usage": {
                            "input_other": resp.usage.input_other,
                            "input_cached": resp.usage.input_cached,
                            "output": resp.usage.output,
                        }
                    }
                    if resp.usage
                    else {}
                ),
                agent_type="proactive_persona",
            )
        except Exception:  # noqa: BLE001
            pass
        return resp

    if timeout:
        return await asyncio.wait_for(_with_stats(), timeout=timeout)
    return await _with_stats()
