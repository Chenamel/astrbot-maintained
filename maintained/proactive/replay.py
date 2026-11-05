"""Replay archived group traffic through the proactive shadow plugin, offline.

The point of this harness is to exercise the *real* handler instead of calling
the judgement model directly.  For every replayed message it builds a genuine
``AstrMessageEvent`` and calls the plugin's own ``on_group_message``, so the
history lookup, the image collection, the JSON parsing and the log write are
the very same code that runs in production.

What is real and what is not
----------------------------
* real: the plugin module loaded from the instance, ``astrbot.core.star.Context``
  (so ``llm_generate`` is core's own method), the chat provider built by core's
  provider factory from the instance config, ``PlatformMessageHistoryManager``
  talking to a real SQLite file, and the archived rows themselves.
* assembled: the event object is a plain ``AstrMessageEvent`` subclass rather
  than an aiocqhttp one, and the provider manager only knows the single judge
  provider.  Neither of those is on the path being measured.
* the archive is opened read-only and copied with ``sqlite3`` backup; the
  per-message context window is produced by trimming a scratch copy, so the
  live database is never written to.

Nothing is ever sent: the plugin runs in ``shadow`` mode and this harness never
calls a send API.

Usage
-----
    # zero-cost smoke test, no model calls
    python maintained/proactive/replay.py --dry-run --sample 6

    # the real thing
    python maintained/proactive/replay.py --sample 500
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import sqlite3
import sys
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace


def _find_instance() -> Path:
    """Locate the AstrBot instance this harness should replay from.

    ``PROACTIVE_INSTANCE`` wins. Otherwise look for the only launcher-managed
    instance that actually has a database, so the harness works on a fresh
    machine without editing this file -- and so the default carries no personal
    path. Returning a nonexistent path is fine: ``main`` turns that into the
    "point me at your instance" message.
    """
    configured = os.environ.get("PROACTIVE_INSTANCE", "").strip()
    if configured:
        return Path(configured).expanduser()
    launcher = Path.home() / ".astrbot_launcher" / "instances"
    try:
        candidates = [
            path
            for path in launcher.iterdir()
            if (path / "core/data/data_v4.db").is_file()
        ]
    except OSError:
        candidates = []
    return candidates[0] if len(candidates) == 1 else Path(".")


INSTANCE = _find_instance()
# The plugin whose handler is replayed. Named through the environment rather
# than in the source: this tree distributes the core only, so a literal plugin
# directory would reference something a reader cannot obtain here.
PLUGIN_NAME = os.environ.get("ASTRBOT_REPLAY_PLUGIN", "my_plugin")
PLUGIN_DIR = INSTANCE / "core/data/plugins" / PLUGIN_NAME
CMD_CONFIG = INSTANCE / "core/data/cmd_config.json"
DB_PATH = INSTANCE / "core/data/data_v4.db"
PLACEHOLDER_SELF = "SELF"
"""Scenario marker for our own bot; replaced at run time by :func:`infer_self_id`."""

SELF_ID = "bot"
"""Our own account id. Set from ``--self-id`` or :func:`infer_self_id` in main."""


def bot_ids() -> set[str]:
    """Ids that count as "us" when reading history back."""
    return {"bot"} | ({SELF_ID} if SELF_ID and SELF_ID != "bot" else set())


def infer_self_id() -> str:
    """Best-effort guess at the account id our bot uses in the archive.

    Rows written by the bot carry ``type: "bot"``; most adapters also store the
    literal ``"bot"`` as the sender, but some store the real account id. No
    number is hardcoded, so this resolves correctly for somebody else's
    instance too. Falls back to ``"bot"``.
    """
    counts: dict[str, int] = {}
    try:
        with closing(sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)) as con:
            for sender, content in con.execute(
                "SELECT sender_id, content FROM platform_message_history"
            ):
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError:
                    continue
                if parsed.get("type") == "bot" and sender and sender != "bot":
                    counts[sender] = counts.get(sender, 0) + 1
    except sqlite3.Error:
        return "bot"
    if counts:
        return max(counts, key=counts.get)
    return "bot"


GROUP_PREFIX = "default:GroupMessage:"

# ``astrbot.api`` must come first: core has a provider <-> context import cycle
# that only resolves when the public API package is imported before the internals.
from astrbot.api import logger  # noqa: E402,F401
from astrbot.core.db.sqlite import SQLiteDatabase  # noqa: E402
from astrbot.core.message.components import (  # noqa: E402
    Forward,
    Image,
    Plain,
    Record,
)
from astrbot.core.platform.astr_message_event import (  # noqa: E402
    AstrMessageEvent,
)
from astrbot.core.platform.astrbot_message import (  # noqa: E402
    AstrBotMessage,
    Group,
    MessageMember,
)
from astrbot.core.platform.message_type import MessageType  # noqa: E402
from astrbot.core.platform.platform_metadata import (  # noqa: E402
    PlatformMetadata,
)
from astrbot.core.platform_message_history_mgr import (  # noqa: E402
    PlatformMessageHistoryManager,
)
from astrbot.core.provider.manager import ProviderManager  # noqa: E402
from astrbot.core.provider.register import provider_cls_map  # noqa: E402
from astrbot.core.star.context import Context  # noqa: E402

try:  # running as a package
    from .scenarios import ME, SCENARIOS, M  # noqa: E402
except ImportError:  # running as a plain script
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from scenarios import ME, SCENARIOS, M  # noqa: E402


# --------------------------------------------------------------------- config
def load_cmd_config() -> dict:
    """Read the instance configuration without letting core rewrite it.

    ``AstrBotConfig`` writes missing defaults back to disk, so the file is read
    as plain JSON instead.
    """
    return json.loads(CMD_CONFIG.read_text(encoding="utf-8-sig"))


def build_provider(provider_id: str, cfg: dict):
    """Instantiate the judge provider exactly the way core does.

    Reuses ``ProviderManager``'s own merge / env-key / dynamic-import helpers,
    so the object is the same class with the same settings as in production.
    """
    sources = cfg.get("provider_sources", [])
    settings = cfg.get("provider_settings", {}) or {}
    entry = next(
        (p for p in cfg.get("provider", []) if p.get("id") == provider_id), None
    )
    if entry is None:
        raise SystemExit(f"实例配置里没有 provider {provider_id!r}")
    shim = SimpleNamespace(provider_sources_config=sources)
    merged = ProviderManager.get_merged_provider_config(shim, entry)
    merged = ProviderManager._resolve_env_key_list(shim, merged)
    ptype = merged["type"]
    if ptype not in provider_cls_map:
        ProviderManager.dynamic_import_provider(shim, ptype)
    return provider_cls_map[ptype].cls_type(merged, settings)


class CannedProvider:
    """Stands in for the judge model during dry runs (no network, no cost)."""

    def __init__(self) -> None:
        self.calls = 0

    async def text_chat(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(
            completion_text='{"decision":"SKIP","reason":"dry-run","draft":""}'
        )


class SingleProviderManager:
    """Minimal stand-in: core's ``llm_generate`` only asks it for one provider."""

    def __init__(self, provider, provider_id: str) -> None:
        self.inst_map = {provider_id: provider}
        # Persona generation falls back to the current provider when no id is
        # given, so the stand-in has to expose one too.
        self.curr_provider_inst = provider

    async def get_provider_by_id(self, provider_id: str):
        return self.inst_map.get(provider_id)


def build_context(db: SQLiteDatabase, provider, provider_id: str) -> Context:
    """A real ``Context`` whose two used collaborators are real objects."""
    return Context(
        event_queue=None,
        config={},
        db=db,
        provider_manager=SingleProviderManager(provider, provider_id),
        platform_manager=None,
        conversation_manager=None,
        message_history_manager=PlatformMessageHistoryManager(db),
        persona_manager=None,
        astrbot_config_mgr=None,
        knowledge_base_manager=None,
        cron_manager=None,
        subagent_orchestrator=None,
    )


def load_plugin(context: Context):
    """Import the shadow plugin from the instance and bind it to our context."""
    spec = importlib.util.spec_from_file_location(
        "replay_plugin_under_test", PLUGIN_DIR / "main.py"
    )
    if spec is None or spec.loader is None:
        raise SystemExit(f"无法加载插件: {PLUGIN_DIR / 'main.py'}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, module.ProactiveShadow(context)


SAMPLE_FORWARD = {
    "messages": [
        {
            "sender": {"nickname": "阿星", "user_id": "10001"},
            "content": [{"type": "text", "data": {"text": "这个报错你们见过吗"}}],
        },
        {
            "sender": {"nickname": "小林", "user_id": "10002"},
            "content": [{"type": "text", "data": {"text": "见过，是版本问题"}}],
        },
        {
            "sender": {"nickname": "阿星", "user_id": "10001"},
            "content": [{"type": "image", "data": {"file": "x.jpg"}}],
        },
    ]
}
"""Roughly what a real OneBot ``get_forward_msg`` returns."""


class FakeBot:
    """Stands in for the OneBot client so expansion can be tested offline."""

    def __init__(self, payload: dict | None = None) -> None:
        self.api = self
        self.payload = payload if payload is not None else SAMPLE_FORWARD
        self.calls: list[tuple] = []

    async def call_action(self, action: str, **params):
        self.calls.append((action, params))
        if action == "get_forward_msg":
            return self.payload
        return {}


class ReplayEvent(AstrMessageEvent):
    """A group message event built from an archived or synthetic row."""

    def __init__(
        self,
        group_id: str,
        sender_id: str,
        sender_name: str,
        components: list,
        message_str: str,
        timestamp: int,
        bot=None,
        message_id: str = "",
    ) -> None:
        self.bot = bot
        obj = AstrBotMessage()
        obj.type = MessageType.GROUP_MESSAGE
        obj.self_id = SELF_ID
        obj.session_id = group_id
        # Distinct ids matter: the plugin remembers them so a reply can
        # quote an earlier message, and the judge numbers the context by
        # position rather than by id.
        obj.message_id = message_id or f"{group_id}-{timestamp}"
        obj.group = Group(group_id=group_id)
        obj.sender = MessageMember(user_id=sender_id, nickname=sender_name)
        obj.message = components
        obj.message_str = message_str
        obj.raw_message = None
        obj.timestamp = timestamp
        meta = PlatformMetadata(
            name="aiocqhttp",
            description="replay",
            id="default",
            support_streaming_message=False,
        )
        super().__init__(message_str, obj, meta, group_id)
        self.role = "member"


def components_for(msg: M) -> list:
    """Turn a synthetic message into real core message components."""
    out: list = []
    if msg.kind == "forward":
        out.append(Forward(id="replay-forward-1"))
    elif msg.kind == "record":
        out.append(Record(file="", url=""))
    elif msg.kind == "image":
        out.append(Image(file="", url=""))
    if msg.plain_text():
        out.append(Plain(text=msg.plain_text()))
    if msg.extra:
        out.append(Plain(text=msg.extra))
    return out or [Plain(text="")]


# ---------------------------------------------------------------- scratch db
def make_scratch(dst_dir: Path, name: str, keep_user_id: str = "") -> Path:
    """Copy the archive into a scratch file. The source is opened read-only.

    ``sqlite3`` backup (instead of a file copy) so pending WAL content is
    included and the live file is never locked or written.
    """
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"{name}.db"
    if dst.exists():
        dst.unlink()
    with (
        closing(sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)) as src,
        closing(sqlite3.connect(str(dst))) as out,
    ):
        src.backup(out)
        if keep_user_id:
            out.execute(
                "DELETE FROM platform_message_history WHERE user_id <> ?",
                (keep_user_id,),
            )
        else:
            out.execute("DELETE FROM platform_message_history")
        out.commit()
    return dst


def trim_after(path: Path, row_id: int) -> None:
    """Drop everything newer than ``row_id`` so the window ends on it.

    Production persists the incoming message before plugin handlers run (see
    ``builtin_stars/astrbot/main.py``, priority ``maxsize - 2``), so the judged
    message is itself the newest row the plugin sees.
    """
    with closing(sqlite3.connect(str(path))) as con:
        con.execute("DELETE FROM platform_message_history WHERE id > ?", (row_id,))
        con.commit()


def insert_rows(path: Path, rows: list[tuple]) -> None:
    """Insert synthetic history rows using core's own column layout."""
    with closing(sqlite3.connect(str(path))) as con:
        con.executemany(
            "INSERT INTO platform_message_history "
            "(platform_id, user_id, sender_id, sender_name, content, "
            "llm_checkpoint_id, created_at, updated_at) "
            "VALUES (?,?,?,?,?,NULL,?,?)",
            rows,
        )
        con.commit()


# ----------------------------------------------------------------- corpus
@dataclass
class Row:
    id: int
    sender_id: str
    sender_name: str
    text: str
    content: dict
    created_at: str


def load_group_rows(user_id: str) -> list[Row]:
    """Read one group's archived messages, oldest first."""
    with closing(sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)) as con:
        raw = con.execute(
            "SELECT id, sender_id, sender_name, content, created_at "
            "FROM platform_message_history WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
    rows: list[Row] = []
    for rid, sender, name, content, created in raw:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            continue
        parts = parsed.get("message") or []
        text = "".join(
            p.get("text", "") for p in parts if p.get("type") == "plain"
        ).strip()
        rows.append(Row(rid, sender or "", name or "", text, parsed, str(created)))
    return rows


def list_groups(min_rows: int = 30) -> list[tuple[str, int]]:
    """Groups in the archive, busiest first."""
    with closing(sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)) as con:
        raw = con.execute(
            "SELECT user_id, COUNT(*) FROM platform_message_history "
            "WHERE user_id LIKE 'default:GroupMessage:%' "
            "GROUP BY user_id HAVING COUNT(*) >= ? ORDER BY COUNT(*) DESC",
            (min_rows,),
        ).fetchall()
    return [(uid, n) for uid, n in raw]


def is_archived_bot(row: Row) -> bool:
    return row.sender_id in bot_ids() or row.content.get("type") == "bot"


def at_bot(content: dict) -> bool:
    return any(
        p.get("type") == "at" and str(p.get("user_id", "")) in bot_ids()
        for p in content.get("message") or []
    )


def allocate(total: int, counts: list[int]) -> list[int]:
    """Split ``total`` across groups in proportion to their size."""
    if not counts or total <= 0:
        return [0 for _ in counts]
    grand = sum(counts) or 1
    exact = [total * c / grand for c in counts]
    out = [int(e) for e in exact]
    for i in sorted(range(len(counts)), key=lambda i: -(exact[i] - out[i]))[
        : total - sum(out)
    ]:
        out[i] += 1
    return out


# ------------------------------------------------------------------- runner
class Runner:
    """Fires events at a plugin instance and keeps track of what came out."""

    def __init__(self, plugin, run_id: str) -> None:
        self.plugin = plugin
        self.run_id = run_id
        self.records: list[dict] = []
        self._orig = plugin._append
        self._tag: dict = {}
        plugin._append = self._append  # type: ignore[method-assign]

    def _append(self, record: dict) -> None:
        record["source"] = "replay"
        record["run_id"] = self.run_id
        record["scenario"] = self._tag.get("scenario", "")
        record["family"] = self._tag.get("family", "")
        record["expect"] = self._tag.get("expect", "")
        record["msg_id"] = self._tag.get("msg_id", "")
        self.records.append(
            {
                "group": record.get("group"),
                "decision": record.get("decision"),
                "reason": record.get("reason", ""),
                "draft": record.get("draft", ""),
                "elapsed_ms": record.get("elapsed_ms"),
                "scenario": record.get("scenario"),
                "family": record.get("family"),
                "expect": record.get("expect"),
                "msg_id": record.get("msg_id"),
                "forward_chars": record.get("forward_chars", 0),
                "current": record.get("current", "")[:80],
            }
        )
        self._orig(record)

    async def fire(self, event, **tag):
        """Run the plugin on one event, recording no-judgement cases too."""
        self._tag = tag
        before = len(self.records)
        await self.plugin.on_group_message(event)
        if len(self.records) == before:
            # Empty text: the plugin returns before the judge is ever called.
            # Recorded as its own outcome so the blind spot stays visible.
            record = {
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "group": event.unified_msg_origin,
                "mode": "shadow",
                "source": "replay",
                "run_id": self.run_id,
                "scenario": tag.get("scenario", ""),
                "family": tag.get("family", ""),
                "expect": tag.get("expect", ""),
                "msg_id": tag.get("msg_id", ""),
                "current": (event.message_str or "")[:80],
                "context": [],
                "images": 0,
                "forward_chars": 0,
                "elapsed_ms": 0,
                "raw": "",
                "decision": "NO_JUDGE",
                "reason": "未进入判定（纯图/转发/语音，文本为空）",
                "draft": "",
            }
            self.records.append(
                {
                    k: record[k]
                    for k in (
                        "group",
                        "decision",
                        "reason",
                        "draft",
                        "elapsed_ms",
                        "scenario",
                        "family",
                        "expect",
                        "msg_id",
                        "forward_chars",
                        "current",
                    )
                }
            )
            self._orig(record)


async def replay_group(
    group: str,
    sample: int,
    provider,
    provider_id: str,
    tmp: Path,
    run_id: str,
    semaphore: asyncio.Semaphore,
    log_path: str = "",
    willingness: bool = False,
):
    """Replay one archived group through its own context and plugin."""
    rows = load_group_rows(group)
    candidates = [
        r for r in rows if not is_archived_bot(r) and r.text and not at_bot(r.content)
    ]
    if not candidates:
        return []
    gid = group.rsplit(":", 1)[-1]
    scratch = make_scratch(tmp, f"g{gid}", keep_user_id=group)
    db = SQLiteDatabase(str(scratch))
    await db.initialize()
    context = build_context(db, provider, provider_id)
    _, plugin = load_plugin(context)
    # The first messages of an archive have no past to look at; skip them so
    # every judged message really sits at the end of a full context window.
    if len(candidates) > plugin.context_size:
        candidates = candidates[plugin.context_size :]
    step = max(1, len(candidates) // sample)
    picked = candidates[::step][:sample]
    # The replay drives messages far faster than a real group, so the
    # rate limits are lifted; the guard logic itself is still exercised.
    plugin.cooldown = 0.0
    plugin.pause_sec = 0.0
    plugin.max_per_hour = 0
    if willingness:
        plugin.willing_enabled = True
    if log_path:
        plugin.log_path = Path(log_path)
    runner = Runner(plugin, run_id)
    for row in picked:
        trim_after(scratch, row.id)
        event = ReplayEvent(
            group_id=gid,
            sender_id=row.sender_id,
            sender_name=row.sender_name,
            components=[Plain(text=row.text)],
            message_str=row.text,
            timestamp=int(time.time()),
            message_id=str(row.id),
        )
        async with semaphore:
            await runner.fire(event, msg_id=str(row.id))
    return runner.records


async def replay_scenarios(
    provider,
    provider_id: str,
    tmp: Path,
    run_id: str,
    semaphore: asyncio.Semaphore,
    keys: list[str] | None,
    log_path: str = "",
    willingness: bool = False,
):
    """Replay the hand-built edge cases, each in its own fake group."""
    scratch = make_scratch(tmp, "scenarios")
    db = SQLiteDatabase(str(scratch))
    await db.initialize()
    context = build_context(db, provider, provider_id)
    _, plugin = load_plugin(context)
    # The replay drives messages far faster than a real group, so the
    # rate limits are lifted; the guard logic itself is still exercised.
    plugin.cooldown = 0.0
    plugin.pause_sec = 0.0
    plugin.max_per_hour = 0
    if willingness:
        plugin.willing_enabled = True
    if log_path:
        plugin.log_path = Path(log_path)
    runner = Runner(plugin, run_id)
    picked = [s for s in SCENARIOS if not keys or s.key in keys]
    base_ts = int(time.time()) - 3600
    for idx, sc in enumerate(picked):
        gid = f"90000{idx:03d}"
        user_id = f"{GROUP_PREFIX}{gid}"
        db_rows = []
        for n, msg in enumerate(sc.messages):
            db_rows.append(
                (
                    "default",
                    user_id,
                    SELF_ID if msg.uid == PLACEHOLDER_SELF else msg.uid,
                    msg.name,
                    json.dumps(
                        {
                            # Anything coming in from the platform is stored as
                            # "user", even when the sender is another bot --
                            # that is exactly why the plugin cannot tell them
                            # apart today (P0).
                            "type": "bot" if msg.uid == ME else "user",
                            "message": msg.parts(),
                        },
                        ensure_ascii=False,
                    ),
                    time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(base_ts + n * 20)
                    ),
                    time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(base_ts + n * 20)
                    ),
                )
            )
        insert_rows(scratch, db_rows)
        target = sc.messages[sc.target]
        target_uid = SELF_ID if target.uid == PLACEHOLDER_SELF else target.uid
        comps = components_for(target)
        # Only forward scenarios get a OneBot client, so the other cases keep
        # exercising the "no adapter support" path.
        bot = FakeBot() if any(isinstance(c, Forward) for c in comps) else None
        event = ReplayEvent(
            group_id=gid,
            sender_id=target_uid,
            sender_name=target.name,
            components=comps,
            message_str=target.plain_text(),
            timestamp=base_ts + len(sc.messages) * 20,
            bot=bot,
            message_id=f"{gid}-{len(sc.messages)}",
        )
        async with semaphore:
            await runner.fire(
                event,
                scenario=sc.key,
                family=sc.family,
                expect=sc.expect,
                msg_id=sc.key,
            )
        # keep only this scenario's rows out of the way of the next one
        with closing(sqlite3.connect(str(scratch))) as con:
            con.execute(
                "DELETE FROM platform_message_history WHERE user_id = ?", (user_id,)
            )
            con.commit()
    return runner.records


# ------------------------------------------------------------------- report
def summarise(records: list[dict], title: str) -> None:
    from collections import Counter

    counts = Counter(r["decision"] for r in records)
    total = len(records) or 1
    print(f"\n=== {title}：{len(records)} 条 ===")
    for key in sorted(counts, key=lambda k: -counts[k]):
        print(f"  {key:11} {counts[key]:4}  ({counts[key] / total:.0%})")
    fam = Counter(r["family"] for r in records if r["family"])
    if fam:
        print("  按场景族：")
        for key in sorted(fam, key=lambda k: -fam[k]):
            sub = [r for r in records if r["family"] == key]
            agree = sum(1 for r in sub if r["decision"] == r["expect"])
            print(f"    {key:14} {fam[key]:3}  与预期一致 {agree}/{len(sub)}")


def selftest() -> int:
    """Deterministic checks on the plugin's parser. No model calls.

    A draft with real newlines used to raise ``Invalid control character``
    inside ``json.loads``, which silently dropped the whole decision. These
    cases pin that down so it cannot come back unnoticed.
    """
    spec = importlib.util.spec_from_file_location(
        "replay_plugin_selftest", PLUGIN_DIR / "main.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # __new__ skips __init__: the parser needs no context.
    plugin = module.ProactiveShadow.__new__(module.ProactiveShadow)

    cases = [
        ('{"decision":"REPLY","reason":"a","draft":"line1\nline2"}', "REPLY"),
        ('```json\n{"decision":"SKIP","reason":"b","draft":""}\n```', "SKIP"),
        ('{"decision":"REPLY","reason":"第一行\n第二行","draft":"x"}', "REPLY"),
        # a stray trailing brace really does happen: it was caught in replay
        (
            '{"decision":"REPLY","reason":"a","draft":"x"}}',
            "REPLY",
        ),
        # Chinese comma between fields (real traffic), plus one inside the
        # text that must survive untouched
        (
            '{"decision":"SKIP","reason":"你好，世界"，"draft":""}',
            "SKIP",
        ),
        # the model sometimes answers with a Python dict instead of JSON
        (
            "{'decision':'REPLY','reason':'x','draft':'y'}",
            "REPLY",
        ),
        ("not json at all", "PARSE_FAIL"),
    ]
    failures = 0
    print("=== 解析器自检（不调模型）===")
    for raw, want in cases:
        got = plugin._parse(raw)
        ok = got["decision"] == want
        failures += 0 if ok else 1
        print(
            f"  {'OK  ' if ok else 'FAIL'} 期望 {want:11} 实际 {got['decision']:11}"
            f" {raw[:34]!r}"
        )
    print(f"  => {len(cases) - failures}/{len(cases)} 通过")
    return 1 if failures else 0


async def main_async(args) -> int:
    cfg = load_cmd_config()
    provider_id = (
        json.loads(
            (
                PLUGIN_DIR.parent.parent / "config" / f"{PLUGIN_DIR.name}_config.json"
            ).read_text(encoding="utf-8-sig")
        ).get("judge_provider_id")
        or "vankit deepseek/deepseek-v4.1-flash"
    )
    print(f"判定 provider: {provider_id}")
    provider = build_provider(provider_id, cfg)
    if args.dry_run:
        # Keep the real provider object (core checks isinstance(Provider)) but
        # short-circuit the network call.
        provider.text_chat = CannedProvider().text_chat
        print("⚠️ dry-run：provider 已实例化，text_chat 替换为空回答，不消耗配额")
    else:
        print("✅ provider 已按 core 的方式实例化：", type(provider).__name__)

    run_id = time.strftime("%Y%m%d-%H%M%S")
    tmp = Path(args.tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(args.concurrency)
    log = args.log or (str(tmp / "shadow_log_dryrun.jsonl") if args.dry_run else "")
    if log:
        print(f"影子日志改写到 {log}")
    all_records: list[dict] = []

    groups = (
        [g for g, _ in list_groups()] if not args.groups else args.groups.split(",")
    )
    counts = []
    for g in groups:
        with closing(sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)) as con:
            n = con.execute(
                "SELECT COUNT(*) FROM platform_message_history WHERE user_id = ?",
                (g,),
            ).fetchone()[0]
        counts.append(n)
    quota = allocate(args.sample, counts)
    print(
        "群配额："
        + ", ".join(f"{g.rsplit(':', 1)[-1]}={q}" for g, q in zip(groups, quota))
    )

    started = time.time()
    results = await asyncio.gather(
        *(
            replay_group(
                g, q, provider, provider_id, tmp, run_id, sem, log, args.willingness
            )
            for g, q in zip(groups, quota)
            if q > 0
        )
    )
    for batch in results:
        all_records.extend(batch)
    summarise(all_records, "真实语料回放")

    if not args.no_scenarios:
        scen = await replay_scenarios(
            provider,
            provider_id,
            tmp,
            run_id,
            sem,
            args.scenario.split(",") if args.scenario else None,
            log,
            args.willingness,
        )
        summarise(scen, "极端场景")
        all_records.extend(scen)

    out = (
        Path(args.out)
        if args.out
        else Path(f".workbuddy/proactive_replay_{run_id}.json")
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "dry_run": args.dry_run,
                "provider_id": provider_id,
                "elapsed_sec": int(time.time() - started),
                "records": all_records,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
        newline="\n",
    )
    print(
        f"\n明细已写入 {out}（{len(all_records)} 条，用时 {int(time.time() - started)}s）"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=500, help="真实语料抽样条数")
    ap.add_argument("--groups", default="", help="只回放这些群（逗号分隔 user_id）")
    ap.add_argument("--scenario", default="", help="只跑这些极端场景（逗号分隔 key）")
    ap.add_argument("--no-scenarios", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="不调用模型")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument(
        "--tmp", default=str(Path(os.environ.get("TEMP", ".")) / "proactive_replay")
    )
    ap.add_argument(
        "--log", default="", help="改写影子日志路径（默认仍写插件的 shadow_log.jsonl）"
    )
    ap.add_argument("--out", default="")
    ap.add_argument(
        "--self-id", default="", help="本机器人的账号 id；留空则自动从历史库推断"
    )
    ap.add_argument("--selftest", action="store_true", help="只跑解析器自检，不调模型")
    ap.add_argument(
        "--willingness", action="store_true", help="开启回复意愿值（默认关闭）"
    )
    args = ap.parse_args()
    if not DB_PATH.exists() and not args.selftest:
        print(
            f"找不到实例数据库：{DB_PATH}\n"
            "请用 PROACTIVE_INSTANCE 环境变量指定你的实例目录，例如：\n"
            "  PROACTIVE_INSTANCE=/path/to/instance python maintained/proactive/replay.py"
        )
        return 2
    global SELF_ID
    SELF_ID = args.self_id.strip() or infer_self_id()
    if not args.selftest and not args.dry_run:
        print(f"本机器人 id: {SELF_ID}")
    if args.selftest:
        return selftest()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
