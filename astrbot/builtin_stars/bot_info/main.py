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

import random
import time

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.config.default import VERSION

#: Captured when the plugin is imported, which is close enough to process start
#: for an "uptime" answer and avoids poking at private runtime internals.
_STARTED_AT = time.time()

_UNAVAILABLE = "这个我就不细说了，反正就是个群友。"

#: QQ system emoji ids, one switch each in the config page. Only used on the
#: aiocqhttp platform; other platforms skip the reaction entirely.
REACT_CHOICES: dict[str, str] = {
    "react_182": "182",
    "react_187": "187",
    "react_178": "178",
    "react_179": "179",
    "react_212": "212",
    "react_14": "14",
}


class BotInfo(Star):
    """Expose a tiny, fixed set of facts about the bot itself."""

    def __init__(self, context: Context, config: dict | None = None) -> None:
        super().__init__(context)
        self.config = config or {}

    @filter.llm_tool()
    async def get_bot_info(self, event: AstrMessageEvent) -> str:
        """被问到「你是什么机器人」「用什么模型」「会些什么」时必须先调用本工具取准确信息，不要凭印象编。无需参数。"""
        if not self.config.get("enabled", True):
            return _UNAVAILABLE

        # Field list, not raw config. Each line is a fact the model can restate
        # in its own words; the shape is deliberately plain text so the model
        # does not echo JSON back at the group.
        lines: list[str] = [
            "名字：hesder",
            "身份：跑在 AstrBot 上的群聊机器人。AstrBot 是一个开源的聊天机器人框架，"
            "靠插件扩展能力，不是某个大厂产品",
        ]

        try:
            provider = self.context.get_using_provider(event.unified_msg_origin)
            model = provider.get_model() if provider else ""
        except Exception as exc:  # noqa: BLE001 - never break the reply
            logger.debug(f"[bot-info] 取模型失败: {exc}")
            model = ""
        if model:
            lines.append(f"对话模型：{model}")
        lines.append(f"框架版本：AstrBot {VERSION}")

        if self.config.get("include_plugins", True):
            try:
                from astrbot.core.star.star import star_map

                lines.append(f"已装插件：{len(star_map)} 个")
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"[bot-info] 取插件数失败: {exc}")

        if self.config.get("include_uptime", True):
            minutes = int((time.time() - _STARTED_AT) / 60)
            if minutes >= 60:
                lines.append(f"运行时长：已连续 {minutes // 60} 小时")
            else:
                lines.append(f"运行时长：已连续 {minutes} 分钟")

        if self.config.get("include_abilities", True):
            lines.append(
                "会的事：群聊接话、点歌放歌、把长回复分几条发、记住聊过的事、看图说话"
            )

        await self._maybe_react(event)
        return "\n".join(lines)

    @filter.command("reacttest")
    async def react_test(self, event: AstrMessageEvent, emoji_id: str = ""):
        """管理员校准用：/reacttest 182 试出某个表情 ID 长什么样。"""
        try:
            is_admin = bool(event.is_admin())
        except Exception:  # noqa: BLE001
            is_admin = False
        if not is_admin:
            yield event.plain_result("这个只有管理员能用。")
            return
        if not emoji_id.isdigit():
            yield event.plain_result(
                "用法：/reacttest <表情ID>，例如 /reacttest 182，看看贴出来是哪个表情。"
            )
            return
        try:
            await event.react(emoji_id)
            yield event.plain_result(f"已尝试贴表情 {emoji_id}，看这条消息上的回应。")
        except Exception as exc:  # noqa: BLE001
            yield event.plain_result(f"贴表情失败：{type(exc).__name__}")

    async def _maybe_react(self, event: AstrMessageEvent) -> None:
        """给提问的消息贴一个选中的 QQ 表情；其他平台直接跳过。"""
        if not self.config.get("react_enabled", False):
            return
        if event.get_platform_name() != "aiocqhttp":
            return
        picks = [eid for key, eid in REACT_CHOICES.items() if self.config.get(key)]
        if not picks:
            return
        try:
            await event.react(random.choice(picks))
        except Exception as exc:  # noqa: BLE001 - never break the answer
            logger.debug(f"[bot-info] 贴表情失败: {exc}")
