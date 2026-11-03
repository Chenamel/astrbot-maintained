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
import copy
import time
from pathlib import Path
from typing import Any

from astrbot import logger
from astrbot.core.agent.message import TextPart
from astrbot.core.pipeline.context_utils import call_event_hook
from astrbot.core.provider.entities import IMAGE_CAPTION_MARKER, ProviderRequest
from astrbot.core.star.star_handler import EventType
from astrbot.core.utils.self_identity import self_identity_note

__all__ = ["generate_with_persona"]

#: Told to the model when the request carried no usable picture, even though the
#: conversation mentions one. Two failure modes to avoid, and why each wording
#: matters: asking for the picture again ("补个截图吧") is what this whole path
#: was fixed for, and inventing what the picture shows is worse -- so the model
#: is told to skip the topic, not to pretend it can see.
_NO_VISUAL_NOTE = (
    "\n# 关于图片\n"
    "这次请求没有附带任何图片内容，上下文里的 [Image] 只是占位。\n"
    "不要追问图片内容，不要描述图片里有什么，直接就文字部分接着聊。\n"
)


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


async def _prepare_images(
    context: Any,
    event: Any,
    req: ProviderRequest,
    provider: Any,
) -> None:
    """Make this request's pictures usable by the provider that will read them.

    The normal pipeline does three things to an outgoing picture and this path
    did none of them, which is how a proactive reply ended up either shipping a
    full-size screenshot or -- when the caller had no reference to hand -- not
    shipping one at all:

    1. compress and localise it, so a 1080x2400 phone screenshot stops travelling
       at several megabytes per request;
    2. keep it when the provider declares image input;
    3. otherwise caption it with the dedicated vision provider, because a
       text-only model cannot use pixels at all.

    Every step degrades instead of failing: a missing helper (older core, no
    caption provider, unreadable file) leaves the request as it arrived, and the
    reply still goes out. Nothing here invents an error message for the user.
    """
    if not req.image_urls:
        return

    settings: dict = {}
    try:
        config = context.get_config(
            umo=getattr(event, "unified_msg_origin", "") or None
        )
        settings = dict(config.get("provider_settings") or {})
    except Exception as exc:  # noqa: BLE001 - defaults are good enough
        logger.debug("proactive image settings unavailable: %s", exc)

    try:
        from astrbot.core.pipeline.process_stage.method.agent_sub_stages.image_input import (
            prepare_request_images,
        )
        from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
        from astrbot.core.utils.media_utils import (
            IMAGE_COMPRESS_DEFAULT_QUALITY,
            normalize_model_image_max_size,
        )
    except ImportError as exc:  # pragma: no cover - older core
        logger.debug("proactive image preparation unavailable: %s", exc)
        return

    options = settings.get("image_compress_options")
    options = options if isinstance(options, dict) else {}
    quality = options.get("quality")
    if isinstance(quality, bool) or not isinstance(quality, int):
        quality = IMAGE_COMPRESS_DEFAULT_QUALITY
    max_size = normalize_model_image_max_size(options.get("max_size"))

    try:
        await prepare_request_images(
            req,
            event,
            enabled=settings.get("image_compress_enabled", True) is not False,
            max_size=max_size,
            quality=min(max(quality, 1), 100),
            output_dir=Path(get_astrbot_temp_path()),
            prepared={},
            montage_max_size=max_size,
        )
    except Exception as exc:  # noqa: BLE001 - a picture must not break the reply
        logger.warning("proactive image preparation skipped: %s", exc)

    # From here the request may still carry local file paths; a provider that
    # cannot read them must not be handed them. When the capability cannot be
    # determined at all, keep the pictures: that matches how core reads an
    # unconfigured ``modalities`` list, and dropping them would be the silent
    # regression this whole helper exists to prevent.
    try:
        from astrbot.core.astr_main_agent_quote import _provider_supports_modality

        supports_image = _provider_supports_modality(provider, "image")
    except Exception as exc:  # noqa: BLE001 - unknown means "let it through"
        logger.debug("proactive image modality unknown, assuming image input: %s", exc)
        return
    if supports_image:
        logger.info(
            "proactive image: sent to provider | count=%d max_size=%d quality=%d",
            len(req.image_urls),
            max_size,
            min(max(quality, 1), 100),
        )
        return

    caption_provider_id = settings.get("default_image_caption_provider_id") or ""
    if caption_provider_id:
        # Deliberately not ``_ensure_img_caption``: on failure that one appends
        # IMAGE_INPUT_UNAVAILABLE_NOTICE, which makes the provider short-circuit
        # and answer "当前看不到图片，请重新发送。" without calling the model. Fine
        # when a user asked about a picture, absurd when the bot speaks first.
        try:
            from astrbot.core.astr_main_agent import _request_img_caption

            caption = await _request_img_caption(
                caption_provider_id,
                settings,
                list(req.image_urls),
                context,
            )
        except Exception as exc:  # noqa: BLE001 - captioning is an upgrade
            logger.warning("proactive image caption failed: %s", exc)
            caption = ""
        if isinstance(caption, str) and caption.strip():
            req.extra_user_content_parts.append(
                TextPart(
                    text=f"{IMAGE_CAPTION_MARKER}{caption.strip()}</image_caption>"
                )
            )

    # Whatever happened above, this provider cannot read these paths.
    req.image_urls = []

    captioned = _has_caption(req)
    noted = False
    if not captioned and _prompt_mentions_image(req):
        req.system_prompt = (req.system_prompt or "") + _NO_VISUAL_NOTE
        noted = True
    logger.info(
        "proactive image: text only | captioned=%s notice=%s",
        captioned,
        noted,
    )


def _has_caption(req: ProviderRequest) -> bool:
    """Return whether the request already carries a picture description."""
    for part in req.extra_user_content_parts or ():
        text = getattr(part, "text", None)
        if not isinstance(text, str) and isinstance(part, dict):
            text = part.get("text")
        if isinstance(text, str) and IMAGE_CAPTION_MARKER in text:
            return True
    return False


def _prompt_mentions_image(req: ProviderRequest) -> bool:
    """Return whether the text this request carries refers to a picture."""
    text = f"{req.prompt or ''}\n{req.system_prompt or ''}"
    return "[Image]" in text or "[图片]" in text


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
    # The persona chain lives in core, not in this module: the normal agent path
    # applies it from a conversation context, which a one-shot call has none of.
    # Without this the bot answered proactive messages with no persona at all --
    # the configured 1.3k-character description only reached @-mentions.
    try:
        persona_manager = getattr(context, "persona_manager", None)
        if persona_manager is not None:
            _, persona, _, _ = await persona_manager.resolve_selected_persona(
                umo=getattr(event, "unified_msg_origin", "") or "",
                conversation_persona_id=None,
                platform_name=getattr(event, "get_platform_name", lambda: "")() or "",
            )
            if persona:
                if persona_prompt := persona.get("prompt"):
                    req.system_prompt += (
                        f"\n# Persona Instructions\n\n{persona_prompt}\n"
                    )
                begin_dialogs = persona.get("_begin_dialogs_processed") or []
                if begin_dialogs:
                    req.contexts[:0] = copy.deepcopy(begin_dialogs)
    except Exception as exc:  # noqa: BLE001 - a missing persona must not block
        logger.warning("proactive persona injection skipped: %s", exc)

    # This path builds its own request and never runs _append_system_reminders,
    # so the identity invariant has to be stated here too -- a proactive reply
    # is exactly where "somebody else's line is mine" gets invented.
    identity = self_identity_note(event)
    if identity:
        req.system_prompt += f"\n{identity}\n"

    # Plugins mutate req here: persona, memory, group context.
    if await call_event_hook(event, EventType.OnLLMRequestEvent, req):
        return None

    # After the hook, so pictures a plugin attached there are covered too --
    # the same order the normal pipeline uses (internal.py prepares, calls the
    # hook, then prepares again for whatever the hook added).
    await _prepare_images(context, event, req, provider)

    coro = provider.text_chat(
        prompt=req.prompt,
        system_prompt=req.system_prompt,
        image_urls=req.image_urls,
        contexts=req.contexts or None,
    )

    async def _with_stats():
        start_time = time.time()
        resp = await coro
        end_time = time.time()
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
                        },
                        "start_time": start_time,
                        "end_time": end_time,
                    }
                    if resp.usage
                    else {
                        "start_time": start_time,
                        "end_time": end_time,
                    }
                ),
                agent_type="proactive_persona",
            )
        except Exception:  # noqa: BLE001
            pass
        return resp

    if timeout:
        return await asyncio.wait_for(_with_stats(), timeout=timeout)
    return await _with_stats()
