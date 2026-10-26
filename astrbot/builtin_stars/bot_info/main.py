"""Built-in tool: answer "what are you" questions with a fixed whitelist.

Group members keep asking what the bot is, which model it runs, and what it can
do. Answering from imagination produces nonsense; dumping configuration would
leak API keys and internal paths. This sits in between.

Security properties, in order of importance:

1. **The tool takes no arguments.** The model cannot ask for a field, so no
   amount of prompting can make it read something outside this file.
2. **Only fixed values are read** -- version, model name, plugin count, uptime.
   Configuration is never serialised, not even filtered.
3. **The switch fails closed in wording**: when disabled, the reply is a plain
   "not available" rather than revealing that a switch exists.
4. **No file paths, keys, base URLs or group ids appear anywhere** in the
   composed string.
"""

from __future__ import annotations

import time

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.config.default import VERSION

#: Captured when the plugin is imported, which is close enough to process start
#: for an "uptime" answer and avoids poking at private runtime internals.
_STARTED_AT = time.time()

_UNAVAILABLE = "这个我就不细说了，反正就是个群友。"


class BotInfo(Star):
    """Expose a tiny, fixed set of facts about the bot itself."""

    def __init__(self, context: Context, config: dict | None = None) -> None:
        super().__init__(context)
        self.config = config or {}

    @filter.llm_tool()
    async def get_bot_info(self, event: AstrMessageEvent) -> str:
        """当群友问你是什么机器人、用什么模型、会些什么的时候，获取自身的基本信息。无需参数，返回固定字段。"""
        if not self.config.get("enabled", True):
            return _UNAVAILABLE

        facts: list[str] = [f"AstrBot {VERSION}"]

        try:
            provider = self.context.get_using_provider(event.unified_msg_origin)
            model = provider.get_model() if provider else ""
        except Exception as exc:  # noqa: BLE001 - never break the reply
            logger.debug(f"[bot-info] 取模型失败: {exc}")
            model = ""
        if model:
            facts.append(f"对话模型 {model}")

        if self.config.get("include_plugins", True):
            try:
                from astrbot.core.star.star import star_map

                facts.append(f"装了 {len(star_map)} 个插件")
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"[bot-info] 取插件数失败: {exc}")

        if self.config.get("include_uptime", True):
            minutes = int((time.time() - _STARTED_AT) / 60)
            if minutes >= 60:
                facts.append(f"已经连续跑了 {minutes // 60} 小时")
            else:
                facts.append(f"已经连续跑了 {minutes} 分钟")

        return "；".join(facts)
