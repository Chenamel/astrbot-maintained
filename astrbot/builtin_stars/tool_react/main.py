"""Built-in: signal that a tool ran, using a reaction instead of a text line.

AstrBot can print "🔨 调用工具: web_search" for every call. That proves the tool
really ran, but a chatty agent turns it into wallpaper. This hook keeps the
signal and drops the noise: it reacts to the triggering message instead.



Some tools do something visible on their own -- playing a song, sending lyrics --
where a paragraph of "I have played it for you" adds nothing. This hook reacts
to the triggering message instead, like a group member would.

This is an *additional* way of acknowledging a finished action, not a
replacement for the reply: the model still says whatever it would have said.
The tool result is never rewritten, because suppressing the answer would
interfere with normal behaviour.

The emoji list is a fallback chain: try the first, and if the protocol layer
rejects it, try the next. When every id fails, nothing happens.

Scope is deliberately narrow:

* QQ only (``aiocqhttp``) -- other platforms have no such reaction concept.
* Only tools listed in ``REACTABLE_TOOLS``; anything else is untouched.
* Any failure is swallowed and logged at debug level, never surfaced.
"""

from __future__ import annotations

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

#: Tools that are never worth a signal (internal bookkeeping).
EXCLUDED_TOOLS: frozenset[str] = frozenset()


def _parse_ids(raw: str) -> list[str]:
    """Turn ``"182, 187"`` into ``["182", "187"]``, dropping anything odd."""
    return [
        part.strip() for part in str(raw or "").split(",") if part.strip().isdigit()
    ]


def _parse_names(raw: str) -> set[str]:
    """Turn ``"web_search, play_song_by_name"`` into a set of tool names."""
    return {part.strip() for part in str(raw or "").split(",") if part.strip()}


class ToolReact(Star):
    """React to the user's message when certain tools finish successfully."""

    def __init__(self, context: Context, config: dict | None = None) -> None:
        super().__init__(context)
        self.config = config or {}

    @filter.on_llm_tool_respond()
    async def on_tool_respond(
        self, event: AstrMessageEvent, tool, tool_args, tool_result
    ):
        """工具执行完就贴表情：按配置顺序尝试，第一个成功即停。"""
        if not self.config.get("enabled", False):
            return
        if event.get_platform_name() != "aiocqhttp":
            return

        name = getattr(tool, "name", "") or ""
        if name in EXCLUDED_TOOLS:
            return

        only = _parse_names(self.config.get("only_tools") or "")
        if only and name not in only:
            return

        ids = _parse_ids(self.config.get("emoji_ids") or "")
        if not ids:
            return

        for emoji_id in ids:
            try:
                await event.react(emoji_id)
            except Exception as exc:  # noqa: BLE001 - try the next id
                logger.debug(f"[tool-react] 表情 {emoji_id} 失败: {exc}")
                continue
            logger.debug(f"[tool-react] {name} 完成，已贴表情 {emoji_id}")
            return
