"""Built-in: express a finished tool action with a message reaction.

Some tools do something visible on their own -- playing a song, sending lyrics --
where a paragraph of "I have played it for you" adds nothing. This hook reacts
to the triggering message instead, like a group member would.

The emoji list is a fallback chain: try the first, and if the protocol layer
rejects it, try the next. Only when every id fails does the answer stay a
normal sentence.

Scope is deliberately narrow:

* QQ only (``aiocqhttp``) -- other platforms have no such reaction concept.
* Only tools listed in ``REACTABLE_TOOLS``; anything else is untouched.
* Any failure is swallowed and logged at debug level, never surfaced.
"""

from __future__ import annotations

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

#: Tool name -> which configured id list applies to it.
REACTABLE_TOOLS: dict[str, str] = {
    "play_song_by_name": "play_song_ids",
    "query_lyrics_by_name": "play_song_ids",
}

#: Replaces the tool result so the model does not narrate what the reaction
#: already said.
_QUIET_RESULT = "（已经用表情回应了，不用再用文字说这件事）"


def _parse_ids(raw: str) -> list[str]:
    """Turn ``"182, 187"`` into ``["182", "187"]``, dropping anything odd."""
    return [
        part.strip() for part in str(raw or "").split(",") if part.strip().isdigit()
    ]


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
        list_key = REACTABLE_TOOLS.get(name)
        if not list_key:
            return

        ids = _parse_ids(self.config.get(list_key) or "")
        if not ids:
            return

        for emoji_id in ids:
            try:
                await event.react(emoji_id)
            except Exception as exc:  # noqa: BLE001 - try the next id
                logger.debug(f"[tool-react] 表情 {emoji_id} 失败: {exc}")
                continue
            logger.debug(f"[tool-react] {name} 完成，已贴表情 {emoji_id}")
            if self.config.get("quiet_after_react", True):
                self._quiet(tool_result)
            return

    @staticmethod
    def _quiet(tool_result) -> None:
        """Replace the tool result so the model stays silent about it."""
        try:
            from mcp.types import TextContent

            tool_result.content = [TextContent(type="text", text=_QUIET_RESULT)]
        except Exception as exc:  # noqa: BLE001 - narration is a nice-to-have
            logger.debug(f"[tool-react] 改写工具结果失败: {exc}")
