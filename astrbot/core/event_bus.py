"""事件总线, 用于处理事件的分发和处理
事件总线是一个异步队列, 用于接收各种消息事件, 并将其发送到Scheduler调度器进行处理
其中包含了一个无限循环的调度函数, 用于从事件队列中获取新的事件, 并创建一个新的异步任务来执行管道调度器的处理逻辑

class:
    EventBus: 事件总线, 用于处理事件的分发和处理

工作流程:
1. 维护一个异步队列, 来接受各种消息事件
2. 无限循环的调度函数, 从事件队列中获取新的事件, 打印日志并创建一个新的异步任务来执行管道调度器的处理逻辑
"""

import asyncio
import re
from asyncio import Queue

from astrbot.core import logger
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.pipeline.scheduler import PipelineScheduler

from .platform import AstrMessageEvent

NEWLINE_MARK = "⏎"
"""Visible stand-in for a newline inside a logged message."""

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")
"""Other invisible characters: they break a log line just as a newline does."""


def _collapse_newlines(text: str) -> str:
    """Render newlines as a visible mark so one message stays one log line.

    Args:
        text: Message outline as produced by the event.

    Returns:
        The same text with every newline replaced by ``NEWLINE_MARK`` and other
        control characters dropped. Only the log copy is touched; the event
        keeps its original text.
    """
    collapsed = (
        text.replace("\r\n", NEWLINE_MARK)
        .replace("\n", NEWLINE_MARK)
        .replace("\r", NEWLINE_MARK)
    )
    # Newlines are marked so the shape stays readable; the remaining control
    # characters carry nothing a human can read, and they split a log line just
    # as a newline does.
    return _CONTROL_CHAR_RE.sub("", collapsed)


class EventBus:
    """用于处理事件的分发和处理"""

    def __init__(
        self,
        event_queue: Queue,
        pipeline_scheduler_mapping: dict[str, PipelineScheduler],
        astrbot_config_mgr: AstrBotConfigManager,
    ) -> None:
        self.event_queue = event_queue  # 事件队列
        # abconf uuid -> scheduler
        self.pipeline_scheduler_mapping = pipeline_scheduler_mapping
        self.astrbot_config_mgr = astrbot_config_mgr
        # 持有正在执行的 pipeline 任务的强引用, 防止 task 在 pending 状态被 GC 回收
        self._pending_tasks: set[asyncio.Task] = set()

    async def dispatch(self) -> None:
        while True:
            event: AstrMessageEvent = await self.event_queue.get()
            conf_info = self.astrbot_config_mgr.get_conf_info(event.unified_msg_origin)
            conf_id = conf_info["id"]
            conf_name = conf_info.get("name") or conf_id
            self._print_event(event, conf_name)
            scheduler = self.pipeline_scheduler_mapping.get(conf_id)
            if not scheduler:
                logger.error(
                    f"PipelineScheduler not found for id: {conf_id}, event ignored."
                )
                continue
            task = asyncio.create_task(scheduler.execute(event))
            self._pending_tasks.add(task)
            task.add_done_callback(self._on_task_done)

    def _on_task_done(self, task: asyncio.Task) -> None:
        """pipeline 任务结束回调: 移除强引用并暴露未捕获的异常"""
        self._pending_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("Pipeline task failed.", exc_info=exc)

    def _escape_message_newlines(self) -> bool:
        """Whether message newlines should be collapsed before logging.

        Returns:
            The configured value, defaulting to True so a config written before
            this option existed still gets the readable behaviour.
        """
        try:
            conf = self.astrbot_config_mgr.default_conf
            return bool(conf.get("log_escape_message_newlines", True))
        except Exception:  # noqa: BLE001 - logging must never break dispatch
            return True

    def _print_event(self, event: AstrMessageEvent, conf_name: str) -> None:
        """用于记录事件信息

        Args:
            event (AstrMessageEvent): 事件对象

        """
        # 换行转义只影响日志副本，event 里的文本保持原样（插件读到的仍是原文）。
        outline = event.get_message_outline()
        if self._escape_message_newlines():
            outline = _collapse_newlines(outline)
        # 如果有发送者名称: [平台名] 发送者名称/发送者ID: 消息概要
        if event.get_sender_name():
            logger.info(
                f"[{conf_name}] [{event.get_platform_id()}({event.get_platform_name()})] {event.get_sender_name()}/{event.get_sender_id()}: {outline}",
                extra={"category": "user_chat"},
            )
        # 没有发送者名称: [平台名] 发送者ID: 消息概要
        else:
            logger.info(
                f"[{conf_name}] [{event.get_platform_id()}({event.get_platform_name()})] {event.get_sender_id()}: {outline}",
                extra={"category": "user_chat"},
            )
