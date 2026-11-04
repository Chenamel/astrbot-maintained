"""Versioned QQ direct turns; original events remain the authorization source."""

import asyncio
import json
import time
from dataclasses import dataclass, field

from astrbot.api.event.extras import (
    is_active_reply,
    owned_image_urls,
    owned_quote_image_urls,
)
from astrbot.core import logger
from astrbot.core.message.components import At, Image, Plain, Reply

#: Default aggregation window: quiet period after the last message, and the hard
#: ceiling measured from the first message of the turn.
DEFAULT_QUIET_SEC = 4
DEFAULT_MAX_WAIT_SEC = 15

#: Upper bound on events retained per turn.
MAX_TRACKED_EVENTS = 30

#: Poll interval used while waiting for the aggregation window to close.
CHANGE_POLL_INTERVAL_SEC = 0.25

#: Upper bound on image URLs carried by one merged turn.
MAX_TURN_IMAGE_URLS = 2

#: Maximum number of task-text characters kept for delivery checks.
TASK_TEXT_MAX_CHARS = 16000

#: How long to wait for another turn's in-flight tool result.
TOOL_RESULT_WAIT_TIMEOUT_SEC = 15


def self_id_of(event) -> str:
    """Return the bot's own id for an event, or ``""`` when unavailable.

    Args:
        event: A message event, or any duck-typed stand-in.

    Returns:
        The bot id as a string; ``""`` when the event cannot provide one.
    """
    getter = getattr(event, "get_self_id", None)
    if not callable(getter):
        return ""
    return str(getter())


def mentions_other(event) -> bool:
    """Return whether any At/Reply in the message targets another account.

    Args:
        event: A message event whose components are scanned.

    Returns:
        True when an At or Reply points at an id other than the bot's own.
    """
    self_id = self_id_of(event)
    return any(
        isinstance(component, At)
        and str(component.qq) != self_id
        or isinstance(component, Reply)
        and str(component.sender_id) != self_id
        for component in event.get_messages()
    )


def mentions_self(event) -> bool:
    """Return whether any At/Reply in the message targets the bot itself.

    Args:
        event: A message event whose components are scanned.

    Returns:
        True when an At or Reply points at the bot's own id.
    """
    self_id = self_id_of(event)
    return any(
        isinstance(component, At)
        and str(component.qq) == self_id
        or isinstance(component, Reply)
        and str(component.sender_id) == self_id
        for component in event.get_messages()
    )


@dataclass
class DirectTurn:
    first_at: float
    last_at: float
    events: list = field(default_factory=list)
    owner: object = None
    version: int = 0
    sent: bool = False
    closed: bool = False
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    tools: dict = field(default_factory=dict)


class DirectTurnCoordinator:
    def __init__(
        self,
        clock=time.monotonic,
        quiet_sec=DEFAULT_QUIET_SEC,
        max_wait_sec=DEFAULT_MAX_WAIT_SEC,
    ):
        self.clock = clock
        self.quiet_sec = quiet_sec
        self.max_wait_sec = max_wait_sec
        self.enabled = quiet_sec > 0
        self.turns = {}
        self.proactive = {}
        #: Per-conversation overrides, set by :meth:`configure_for`.
        #:
        #: One coordinator serves the whole process, but the window is a config
        #: value and a process can serve several bots. Reading one shared field
        #: meant the last message's profile silently rewrote everyone else's.
        self.windows: dict[str, tuple[float, bool]] = {}

    def configure(self, quiet_sec: object, origin: str | None = None) -> None:
        """Apply the aggregation window from the running configuration.

        Args:
            quiet_sec: Seconds to wait after the last message of a turn. Zero
                disables aggregation entirely, so each message is handled on
                its own. Unknown or invalid values leave the window unchanged.
            origin: Conversation this window belongs to. When given, the value
                is stored for that conversation only; when omitted it becomes
                the process-wide default, which is what tests and single-bot
                deployments want.
        """
        if isinstance(quiet_sec, bool) or not isinstance(quiet_sec, (int, float)):
            return
        if quiet_sec < 0:
            return
        seconds = float(quiet_sec)
        # A zero-second window must also stop observe() from tracking turns:
        # otherwise the first message is released instantly while the next one
        # still invalidates it, which is worse than not aggregating at all.
        enabled = seconds > 0
        if origin is None:
            self.quiet_sec = seconds
            self.enabled = enabled
            return
        self.windows[origin] = (seconds, enabled)

    def window_for(self, origin: str) -> tuple[float, bool]:
        """Return the aggregation window that applies to a conversation.

        Args:
            origin: The conversation's unified message origin.

        Returns:
            ``(seconds, enabled)`` for that conversation, falling back to the
            process default when its profile has not been seen yet.
        """
        return self.windows.get(origin, (self.quiet_sec, self.enabled))

    def key(self, event):
        return event.unified_msg_origin, str(event.get_sender_id())

    def eligible(self, event):
        origin = getattr(event, "unified_msg_origin", "") or ""
        _, enabled = self.window_for(origin)
        return (
            enabled
            and getattr(event, "get_platform_name", lambda: "")() == "aiocqhttp"
            and bool(event.get_sender_id())
        )

    def _invalidate(self, turn):
        if turn.owner is not None and not turn.sent:
            turn.owner.set_extra("agent_stop_requested", True)
            turn.owner.stop_event()
        turn.changed.set()

    def reset(self, origin):
        active = self.proactive.pop(origin, None)
        if active:
            active[0].set_extra("_turn_superseded", True)
            active[1]()
        for key, turn in list(self.turns.items()):
            if key[0] == origin:
                turn.closed = True
                self._invalidate(turn)
                self.turns.pop(key, None)

    def reset_all(self):
        for origin in {key[0] for key in self.turns} | set(self.proactive):
            self.reset(origin)

    def observe(self, event, wake_prefixes=()):
        if not self.eligible(event):
            return
        text = (event.get_message_str() or "").strip()
        if text.startswith("/"):
            if text.split()[0] in ("/new", "/reset"):
                self.reset(event.unified_msg_origin)
            return
        if not text:
            # Resolve once: the comprehension below re-checked self_id_of() for
            # every component of every text-less message.
            self_id = self_id_of(event)
            if not any(
                isinstance(c, Image) or isinstance(c, At) and str(c.qq) == self_id
                for c in event.get_messages()
            ):
                return
        active = self.proactive.get(event.unified_msg_origin)
        if active and active[0] is not event:
            active[0].set_extra("_turn_superseded", True)
            active[0].set_extra("agent_stop_requested", True)
            active[0].stop_event()
            active[1]()
        turn = self.turns.get(self.key(event))
        if turn and any(
            str(old.message_obj.message_id) == str(event.message_obj.message_id)
            for old in turn.events
        ):
            event.stop_event()
            return
        other = mentions_other(event)
        if (
            (not turn or turn.closed or turn.sent)
            and not other
            and (
                event.is_private_chat()
                or event.is_at_or_wake_command
                or mentions_self(event)
                or any(text.startswith(prefix) for prefix in wake_prefixes if prefix)
            )
        ):
            now = self.clock()
            turn = DirectTurn(now, now, [event], version=1)
            self.turns[self.key(event)] = turn
            event.set_extra("_direct_turn_state", turn)
            event.set_extra("_direct_turn_version", 1)
            return
        if turn and not turn.closed and not turn.sent and not other:
            # Invalidate before plugin hooks or the session lock can delay this event.
            self._invalidate(turn)
            if turn.owner is not None:
                turn.first_at = self.clock()
                turn.owner = None
            turn.version += 1
            turn.last_at = self.clock()
            turn.events.append(event)
            if len(turn.events) > MAX_TRACKED_EVENTS:
                turn.events[1:2] = []
            event.set_extra("_direct_turn_state", turn)
            event.set_extra("_direct_turn_version", turn.version)
            event.set_extra("_direct_turn_supplement", True)
            event.is_at_or_wake_command = True
            # DEBUG: this fires once per follow-up message, so at INFO a lively
            # group buries everything else in the log.
            logger.debug(
                "Direct turn replaced | message_id=%s version=%s messages=%s",
                event.message_obj.message_id,
                turn.version,
                len(turn.events),
            )

    async def collect(self, event):
        if not self.eligible(event) or is_active_reply(event):
            return True
        if (event.get_message_str() or "").strip().startswith("/"):
            return True
        turn = event.get_extra("_direct_turn_state")
        if turn is None:
            now = self.clock()
            turn = DirectTurn(now, now, [event], version=1)
            self.turns[self.key(event)] = turn
            event.set_extra("_direct_turn_state", turn)
            event.set_extra("_direct_turn_version", 1)
        version = event.get_extra("_direct_turn_version")
        # The window is a per-conversation config value; reading the shared
        # field here would let a busy second bot shorten this conversation's
        # wait to nothing.
        quiet_sec, _ = self.window_for(getattr(event, "unified_msg_origin", "") or "")
        while not turn.closed and version == turn.version and not event.is_stopped():
            remaining = (
                min(
                    turn.first_at + self.max_wait_sec,
                    turn.last_at + quiet_sec,
                )
                - self.clock()
            )
            if remaining <= 0:
                turn.owner = event
                self.prepare(event)
                # DEBUG for the same reason as "replaced" above: one line per
                # answered turn is not worth an INFO slot.
                logger.debug(
                    "Direct turn collected | message_id=%s version=%s messages=%s images=%s",
                    event.message_obj.message_id,
                    version,
                    len(turn.events),
                    len(event.get_extra("_direct_turn_image_urls", [])),
                )
                return True
            turn.changed.clear()
            try:
                await asyncio.wait_for(
                    turn.changed.wait(), min(remaining, CHANGE_POLL_INTERVAL_SEC)
                )
            except TimeoutError:
                pass
        return False

    def prepare(self, event):
        turn = event.get_extra("_direct_turn_state")
        if not turn:
            return
        refs = []
        lines = []
        task_texts = []
        for source in turn.events:
            message_id = str(source.message_obj.message_id)
            text = " ".join(
                c.text for c in source.get_messages() if isinstance(c, Plain)
            )
            task_texts.append(text)
            quotes = [
                f"quote author={c.sender_id} id={c.id}: {c.message_str or ''}"
                for c in source.get_messages()
                if isinstance(c, Reply)
            ]
            owned_quotes = owned_quote_image_urls(source)
            for component in source.get_messages():
                if isinstance(component, Reply):
                    quote_refs = owned_quotes.get(str(component.id), [])
                    refs.extend(
                        quote_refs
                        or [
                            str(c.url or c.file or "")
                            for c in component.chain or []
                            if isinstance(c, Image)
                        ]
                    )
            lines.append(
                f"message {message_id}: {text}"
                + ("\n" + "\n".join(quotes) if quotes else "")
            )
            owned = owned_image_urls(source)
            refs.extend(
                owned
                or [
                    str(c.url or c.file or "")
                    for c in source.get_messages()
                    if isinstance(c, Image)
                ]
            )
        current_quotes = owned_quote_image_urls(event)
        priority_refs = [ref for values in current_quotes.values() for ref in values]
        event.set_extra(
            "_direct_turn_image_urls",
            list(dict.fromkeys(priority_refs + refs))[:MAX_TURN_IMAGE_URLS],
        )
        event.set_extra("_direct_turn_text", "\n".join(lines))
        event.set_extra(
            "_direct_turn_task_text", "\n".join(task_texts)[-TASK_TEXT_MAX_CHARS:]
        )

    def finish(self, event):
        turn = event.get_extra("_direct_turn_state")
        if turn and is_current(event) and (turn.owner is event or event.is_stopped()):
            turn.closed = True
            if self.turns.get(self.key(event)) is turn:
                self.turns.pop(self.key(event), None)


coordinator = DirectTurnCoordinator()


def _extra(event, name, default=None):
    getter = getattr(event, "get_extra", None)
    if getter is None:
        return default
    try:
        value = getter(name, default)
    except TypeError:
        value = getter(name)
    return default if value is None else value


def is_current(event):
    if _extra(event, "_turn_superseded", False) is True:
        return False
    turn = _extra(event, "_direct_turn_state")
    return not isinstance(turn, DirectTurn) or (
        not turn.closed and _extra(event, "_direct_turn_version") == turn.version
    )


def mark_sent(event):
    turn = _extra(event, "_direct_turn_state")
    if turn and is_current(event):
        turn.sent = True


def _tool_key(name, args):
    return name, json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)


def get_tool_result(event, name, args):
    turn = _extra(event, "_direct_turn_state")
    entry = turn.tools.get(_tool_key(name, args)) if turn else None
    return (True, entry[1]) if entry and entry[0].is_set() else (False, "")


def begin_tool(event, name, args):
    turn = _extra(event, "_direct_turn_state")
    if not turn:
        return True
    key = _tool_key(name, args)
    if key in turn.tools:
        return False
    turn.tools[key] = [asyncio.Event(), ""]
    return True


def record_tool_result(event, name, args, content):
    turn = _extra(event, "_direct_turn_state")
    if turn:
        entry = turn.tools.setdefault(_tool_key(name, args), [asyncio.Event(), ""])
        entry[1] = content
        entry[0].set()


def release_tool(event, name, args):
    turn = _extra(event, "_direct_turn_state")
    if isinstance(turn, DirectTurn):
        entry = turn.tools.get(_tool_key(name, args))
        if entry and not entry[0].is_set():
            turn.tools.pop(_tool_key(name, args), None)


async def wait_tool_result(event, name, args):
    turn = _extra(event, "_direct_turn_state")
    entry = turn.tools.get(_tool_key(name, args)) if turn else None
    if entry:
        try:
            await asyncio.wait_for(entry[0].wait(), TOOL_RESULT_WAIT_TIMEOUT_SEC)
            return entry[1]
        except TimeoutError:
            pass
    return "Previous operation may already have executed. Do not repeat it; completion is unconfirmed."
