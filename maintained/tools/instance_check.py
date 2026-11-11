"""Restart review for a live instance (roadmap item N2).

Reloading a plugin only swaps one module; a full restart is the only way to
prove the whole load chain still comes up clean -- which matters most right
before something starts sending messages for real.

This is deliberately read-only: it reports, it never changes anything. It
reviews ONE plugin's restart, not the health of the whole instance -- for the
daily health report use ``daily_check.py`` instead.

Usage::

    python maintained/tools/instance_check.py --instance "<instance dir>" \
        --plugin <plugin-dir-name> --since "2026-11-06 00:00" \
        --until "2026-11-07 00:00"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from pathlib import Path

LOG_DIR = "core/data/logs"
LOG_GLOB = "astrbot*.log"
DB_PATH = "core/data/data_v4.db"

#: Recently means "after the process started"; used to tell new errors from old.
ERROR_RE = re.compile(r"\[(?:ERRO|CRIT)\]")


def _check(label: str, ok: bool, detail: str) -> bool:
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}: {detail}")
    return ok


def check_files(root: Path, plugin: str = "") -> bool:
    """Check the plugin's files, or skip them when no plugin was given."""
    print("① 文件与配置")
    if not plugin:
        print("        （未指定 --plugin，跳过插件目录与配置检查）")
        return _check("data_v4.db", (root / DB_PATH).is_file(), "存在")
    plugin_dir = f"core/data/plugins/{plugin}"
    config_path = f"core/data/config/{plugin}_config.json"
    ok = True
    for rel in (plugin_dir, config_path, DB_PATH):
        ok &= _check(
            rel.split("/")[-1],
            (root / rel).exists(),
            "存在" if (root / rel).exists() else "缺失",
        )
    cfg = root / config_path
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            ok &= _check("配置可解析", False, str(exc))
            return ok
        ok &= _check("配置可解析", True, f"{len(data)} 项")
        live = data.get("live_groups") or []
        print(f"        live_groups = {live}  ← 真发送的群，留空=全部影子")
        print(f"        willingness = {data.get('willingness_enabled', False)}")
        print(f"        max_per_hour = {data.get('max_per_hour', '未设置')}")
    return ok


def check_log(root: Path, since: str = "", until: str = "") -> bool:
    """Report errors in the half-open window ``[since, until)``.

    Every rotated ``astrbot*.log`` is scanned in full. Reading only the last
    4000 lines of the current file used to hide most of the day's errors, and
    a lower bound without an upper one pulled in errors from the next day.
    """
    print("\n② 日志")
    if since or until:
        print(f"        （只看 {since or '最早'} ~ {until or '现在'}）")
    files = sorted((root / LOG_DIR).glob(LOG_GLOB))
    if not files:
        return _check("日志文件", False, "缺失")
    errors = []
    for path in files:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not ERROR_RE.search(line):
                continue
            stamp = line.lstrip("[").strip()[:19]
            if since and stamp and stamp < since:
                continue
            if until and stamp and stamp >= until:
                continue
            errors.append(line)
    if not errors:
        return _check("错误数", True, "0")
    print(f"        最近 {len(errors)} 条，末尾 3 条：")
    for line in errors[-3:]:
        print(f"        {line[:130]}")
    return _check("错误数", False, f"{len(errors)} 条，见上")


def check_disabled_plugins(root: Path) -> bool:
    """Read the disabled-plugin list as evidence of the default-off policy.

    This deliberately reads no switch value: upstream's ``active_reply.enable``
    and plugin-level switches are independent of that list.
    """
    print("\n③ 默认关闭策略：实例禁用插件列表可读")
    db = root / DB_PATH
    if not db.exists():
        return _check("数据库", False, "缺失")
    try:
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as con:
            row = con.execute(
                "SELECT value FROM preferences WHERE key='inactivated_plugins'"
            ).fetchone()
    except sqlite3.Error as exc:
        return _check("查询禁用列表", False, str(exc))
    disabled = []
    if row:
        try:
            disabled = json.loads(row[0]).get("val", [])
        except json.JSONDecodeError:
            disabled = []
    print(f"        禁用插件: {[d.split('.')[-2] for d in disabled]}")
    return _check("禁用列表可读", True, f"{len(disabled)} 个")


def check_decisions(root: Path, plugin: str = "") -> bool:
    """Check the plugin's decision log; skip it when no plugin was given."""
    print("\n④ 判定是否还在产生")
    if not plugin:
        print("        （未指定 --plugin，跳过判定日志检查）")
        return True
    path = root / f"core/data/plugins/{plugin}/shadow_log.jsonl"
    if not path.exists():
        return _check("判定日志", False, "缺失")
    rows = [
        line
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip()
    ]
    live = 0
    sent = 0
    last = "-"
    for line in rows:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("source") == "replay":
            continue
        live += 1
        if rec.get("sent"):
            sent += 1
        last = rec.get("ts", "-")
    print(f"        线上判定 {live} 条，最新 {last}，已发送 {sent} 条")
    return _check("判定日志可读", live > 0, f"{live} 条")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="只读的实例重启复核")
    ap.add_argument("--instance", required=True, help="实例目录")
    ap.add_argument(
        "--plugin",
        default="",
        help="要复核的插件目录名；留空则跳过插件相关检查（读 ASTRBOT_CHECK_PLUGIN）",
    )
    ap.add_argument(
        "--since",
        default="",
        help="时间窗下界，如 '2026-10-25 01:05'；留空则不限",
    )
    ap.add_argument(
        "--until",
        default="",
        help="时间窗上界（不含），如 '2026-10-26 00:00'；留空则不限",
    )
    args = ap.parse_args(argv)
    plugin = args.plugin or os.environ.get("ASTRBOT_CHECK_PLUGIN", "")
    since = args.since + ":00" if len(args.since) == 16 else args.since[:19]
    until = args.until + ":00" if len(args.until) == 16 else args.until[:19]
    root = Path(args.instance)
    if not root.exists():
        print(f"实例目录不存在: {root}")
        return 2
    print(f"实例: {root}\n")
    results = [
        check_files(root, plugin),
        check_log(root, since, until),
        check_disabled_plugins(root),
        check_decisions(root, plugin),
    ]
    print()
    if all(results):
        print("=> 全部通过")
        return 0
    print("=> 有项目未通过，见上")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
