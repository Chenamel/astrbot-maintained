"""Expand merged forwards of the current message into plain text.

A merged forward reaches the framework as a ``Forward`` component carrying only
an id -- the archive keeps a ``[Forward]`` placeholder, so the content is
recoverable only while the event is still alive. Anything that needs to
understand a forward has to ask the adapter right then.

Expansion is best effort: an adapter that cannot serve the call, or a payload
shape we do not recognise, yields an empty string and the request proceeds as
before. Content is capped, because a forward can be arbitrarily large and every
character costs tokens on the way to the model.
"""

from __future__ import annotations

import asyncio
from typing import Any

from astrbot import logger
from astrbot.core.message.components import Forward
from astrbot.core.platform.astr_message_event import AstrMessageEvent

FORWARD_MAX_CHARS = 1500
"""Cap for the expanded text. Forwards can be huge; this bounds the cost."""

FORWARD_MAX_NODES = 30
"""Cap for the number of nodes rendered from one forward."""

_FORWARD_CALL_TIMEOUT = 10.0

#: Log the first expansion outcome once per process. Whether an adapter
#: serves ``get_forward_msg`` is deployment-specific, so a silent no-op
#: would look identical to "there was no forward at all".
_attribution_logged = False


def _adapter_call(event: AstrMessageEvent):
    """Return the adapter's ``call_action``, or ``None`` when unavailable.

    Args:
        event: The live message event.

    Returns:
        A callable taking ``(action, **params)`` for OneBot-style adapters, else
        ``None``. Platforms without it simply cannot expand forwards.
    """
    bot = getattr(event, "bot", None)
    api = getattr(bot, "api", None)
    call = getattr(api, "call_action", None)
    return call if callable(call) else None


def _render_segments(segments: Any) -> str:
    """Render one node's segment list as readable text.

    Args:
        segments: The node's ``content``: a list of segment dicts, a bare dict,
            or something else entirely.

    Returns:
        Plain text for the node, with non-text segments reduced to markers so
        the reader knows something was there.
    """
    if isinstance(segments, dict):
        segments = [segments]
    if not isinstance(segments, list):
        return ""

    parts: list[str] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        seg_type = str(segment.get("type") or "")
        data = segment.get("data") if isinstance(segment.get("data"), dict) else {}
        text = str(
            segment.get("text")
            or (data.get("text") if isinstance(data, dict) else "")
            or segment.get("content")
            or ""
        )
        if seg_type in ("", "text") and text:
            parts.append(text)
        elif seg_type in ("image", "file", "video", "record"):
            parts.append(f"[{seg_type}]")
        elif seg_type == "forward":
            parts.append("[转发]")
    return "".join(parts).strip()


def _render_payload(payload: Any) -> str:
    """Turn a ``get_forward_msg`` payload into ``name：text`` lines.

    Args:
        payload: The adapter response. Implementations disagree on the shape,
            so both a bare and a ``data``-wrapped payload are accepted.

    Returns:
        Rendered lines, one per node, or an empty string when nothing usable
        was found.
    """
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            payload = data
    nodes = payload.get("messages") if isinstance(payload, dict) else payload
    if not isinstance(nodes, list):
        return ""

    lines: list[str] = []
    for node in nodes[:FORWARD_MAX_NODES]:
        if not isinstance(node, dict):
            continue
        sender = node.get("sender")
        who = ""
        if isinstance(sender, dict):
            who = str(
                sender.get("nickname")
                or sender.get("card")
                or sender.get("user_id")
                or ""
            )
        body = _render_segments(node.get("content"))
        if not body:
            continue
        lines.append(f"{who}：{body}" if who else body)
    return "\n".join(lines)


async def expand_forward_text(
    event: AstrMessageEvent,
    max_chars: int = FORWARD_MAX_CHARS,
) -> str:
    """Expand every merged forward attached to ``event`` into plain text.

    Args:
        event: The live message event. Must be handled before the event dies,
            since the content cannot be recovered afterwards.
        max_chars: Hard cap on the returned text length.

    Returns:
        Rendered text, or an empty string when there is no forward, the adapter
        cannot expand it, or expansion failed. Never raises: a forward that
        cannot be read must not break the reply.
    """
    global _attribution_logged
    forwards = [c for c in event.get_messages() if isinstance(c, Forward)]
    if not forwards:
        return ""
    call = _adapter_call(event)
    if call is None:
        return ""

    chunks: list[str] = []
    for comp in forwards:
        try:
            payload = await asyncio.wait_for(
                call("get_forward_msg", id=comp.id), timeout=_FORWARD_CALL_TIMEOUT
            )
        except Exception as exc:  # noqa: BLE001 - expansion is best effort
            if not _attribution_logged:
                _attribution_logged = True
                logger.info("Forward expansion failed: %s: %s", type(exc).__name__, exc)
            continue
        rendered = _render_payload(payload)
        if rendered:
            chunks.append(rendered)
        if sum(len(chunk) for chunk in chunks) >= max_chars:
            break

    expanded = "\n".join(chunks).strip()[:max_chars]
    if expanded and not _attribution_logged:
        _attribution_logged = True
        logger.info(
            "Forward expansion works: %d chars from %d forward(s)",
            len(expanded),
            len(forwards),
        )
    return expanded
