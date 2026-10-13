"""Quoted-message and attachment helpers for the main agent build.

Extracted from ``astr_main_agent`` by T8-12. The functions are re-exported from
``astr_main_agent`` because both the pipeline stage and the upstream tests
resolve them as module attributes.
"""

from __future__ import annotations

from astrbot.core import logger
from astrbot.core.agent.message import TextPart
from astrbot.core.message.components import Reply
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider import Provider
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.context import Context
from astrbot.core.utils.quoted_message.settings import (
    SETTINGS as DEFAULT_QUOTED_MESSAGE_SETTINGS,
)
from astrbot.core.utils.quoted_message.settings import (
    QuotedMessageParserSettings,
)
from astrbot.core.utils.quoted_message_parser import (
    extract_quoted_message_text,
)

__all__ = [
    "_append_audio_attachment",
    "_append_quoted_audio_attachment",
    "_append_quoted_image_attachment",
    "_get_quoted_message_parser_settings",
    "_process_quote_message",
    "_provider_supports_modality",
]


def _append_quoted_image_attachment(req: ProviderRequest, image_path: str) -> None:
    req.extra_user_content_parts.append(
        TextPart(text=f"[Image Attachment in quoted message: path {image_path}]")
    )


def _append_audio_attachment(req: ProviderRequest, audio_path: str) -> None:
    req.extra_user_content_parts.append(
        TextPart(text=f"[Audio Attachment: path {audio_path}]")
    )


def _append_quoted_audio_attachment(req: ProviderRequest, audio_path: str) -> None:
    req.extra_user_content_parts.append(
        TextPart(text=f"[Audio Attachment in quoted message: path {audio_path}]")
    )


def _get_quoted_message_parser_settings(
    provider_settings: dict[str, object] | None,
) -> QuotedMessageParserSettings:
    if not isinstance(provider_settings, dict):
        return DEFAULT_QUOTED_MESSAGE_SETTINGS
    overrides = provider_settings.get("quoted_message_parser")
    if not isinstance(overrides, dict):
        return DEFAULT_QUOTED_MESSAGE_SETTINGS
    return DEFAULT_QUOTED_MESSAGE_SETTINGS.with_overrides(overrides)


async def _process_quote_message(
    event: AstrMessageEvent,
    req: ProviderRequest,
    img_cap_prov_id: str,
    plugin_context: Context,
    quoted_message_settings: QuotedMessageParserSettings = DEFAULT_QUOTED_MESSAGE_SETTINGS,
    main_provider_supports_image: bool = False,
    skip_quote_image_caption: bool = False,
    image_ref: str | None = None,
) -> None:
    """Append quoted text and optionally describe an explicitly supplied image.

    Args:
        event: Event whose quote text is included in the request.
        req: Working request receiving the quote text and optional caption.
        img_cap_prov_id: Existing dedicated caption provider selection.
        plugin_context: Provider and quoted-message lookup services.
        quoted_message_settings: Existing quote extraction limits and options.
        main_provider_supports_image: Whether the main model can see images.
        skip_quote_image_caption: Whether the main caption branch handles it.
        image_ref: Already collected image reference; the local stage supplies
            a prepared path. No image is re-read from the event here.
    """
    quote = None
    for comp in event.message_obj.message:
        if isinstance(comp, Reply):
            quote = comp
            break
    if not quote:
        return

    content_parts = []
    sender_info = f"({quote.sender_nickname}): " if quote.sender_nickname else ""
    message_str = (
        await extract_quoted_message_text(
            event,
            quote,
            settings=quoted_message_settings,
        )
        or quote.message_str
        or "[Empty Text]"
    )
    content_parts.append(f"{sender_info}{message_str}")

    if image_ref:
        if skip_quote_image_caption:
            logger.debug(
                "Skipping quote image captioning because image captioning already handled this request."
            )
        elif main_provider_supports_image:
            logger.debug(
                "Skipping quote image captioning because the main provider supports image input."
            )
        elif not img_cap_prov_id:
            logger.debug(
                "No dedicated image caption provider configured. "
                "Skipping quote image captioning."
            )
        else:
            try:
                prov = None
                prov = plugin_context.get_provider_by_id(img_cap_prov_id)
                if prov is None:
                    prov = await plugin_context.get_using_provider_async(
                        event.unified_msg_origin
                    )

                if prov and isinstance(prov, Provider):
                    llm_resp = await prov.text_chat(
                        prompt="Please describe the image content.",
                        image_urls=[image_ref],
                    )
                    if llm_resp.completion_text:
                        content_parts.append(
                            f"[Image Caption in quoted message]: {llm_resp.completion_text}"
                        )
                else:
                    logger.warning("No provider found for image captioning in quote.")
            except Exception as exc:
                logger.error("Quote image captioning failed (%s).", type(exc).__name__)

    quoted_content = "\n".join(content_parts)
    quoted_text = f"<Quoted Message>\n{quoted_content}\n</Quoted Message>"
    req.extra_user_content_parts.append(TextPart(text=quoted_text))


def _provider_supports_modality(provider: Provider, modality: str) -> bool:
    modalities = provider.provider_config.get("modalities", None)
    if modalities == []:
        return True  # Empty list from migration is treated as unconfigured for backward compatibility
    return isinstance(modalities, list) and modality in modalities
