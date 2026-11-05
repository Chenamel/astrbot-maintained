"""Restart review for a live instance (roadmap item N2).

Reloading a plugin only swaps one module; a full restart is the only way to
prove the whole load chain still comes up clean -- which matters most right
before something starts sending messages for real.

This is deliberately read-only: it reports, it never changes anything.

Usage::

    python maintained/tools/instance_check.py --instance "<instance dir>"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from pathlib import Path

#: The plugin under inspection, relative to the instance root. Kept out of the
#: source: this repository distributes the core only, and a hard-coded plugin
#: directory would name an artefact a reader cannot obtain here. Point it at
#: whatever plugin you are checking with ``--plugin`` or ``ASTRBOT_CHECK_PLUGIN``.
PLUGIN_NAME = os.environ.get("ASTRBOT_CHECK_PLUGIN", "my_plugin")
PLUGIN_DIR = f"core/data/plugins/{PLUGIN_NAME}"
CONFIG_PATH = f"core/data/config/{PLUGIN_NAME}_config.json"
LOG_PATH = "core/data/logs/astrbot.log"
SHADOW_LOG = f"core/data/plugins/{PLUGIN_NAME}/shadow_log.jsonl"
DB_PATH = "core/data/data_v4.db"

#: Recently means "after the process started"; used to tell new errors from old.
ERROR_RE = re.compile(r"\[(?:ERRO|CRIT)\]")


def _check(label: str, ok: bool, detail: str) -> bool:
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}: {detail}")
    return ok


def check_files(root: Path) -> bool:
    print("① 文件与配置")
    ok = True
    for rel in (PLUGIN_DIR, CONFIG_PATH, DB_PATH):
        ok &= _check(
            rel.split("/")[-1],
            (root / rel).exists(),
            "存在" if (root / rel).exists() else "缺失",
        )
    cfg = root / CONFIG_PATH
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


def check_log(root: Path, since: str = "") -> bool:
    """Report errors, optionally only those logged after ``since``.

    Without ``since`` this would keep re-reporting errors from before the
    restart, which is exactly what a restart review is *not* interested in.
    """
    print("\n② 日志")
    if since:
        print(f"        （只看 {since} 之后，之前的不算）")
    log = root / LOG_PATH
    if not log.exists():
        return _check("日志文件", False, "缺失")
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()[-4000:]
    errors = []
    for line in lines:
        if not ERROR_RE.search(line):
            continue
        if since:
            # Lines start with "[", which would otherwise break the comparison.
            stamp = line.lstrip("[").strip()[: len(since)]
            if stamp and stamp < since:
                continue
        errors.append(line)
    if not errors:
        return _check("错误数", True, "0")
    print(f"        最近 {len(errors)} 条，末尾 3 条：")
    for line in errors[-3:]:
        print(f"        {line[:130]}")
    return _check("错误数", False, f"{len(errors)} 条，见上")


def check_switch(root: Path) -> bool:
    print("\n③ 铁律 6：上游主动回复开关必须恒关闭")
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


def check_decisions(root: Path) -> bool:
    print("\n④ 判定是否还在产生")
    path = root / SHADOW_LOG
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
        "--since",
        default="",
        help="只统计该时刻之后的错误，如 '2026-10-25 01:05'；留空则看全部",
    )
    args = ap.parse_args(argv)
    root = Path(args.instance)
    if not root.exists():
        print(f"实例目录不存在: {root}")
        return 2
    print(f"实例: {root}\n")
    results = [
        check_files(root),
        check_log(root, args.since),
        check_switch(root),
        check_decisions(root),
    ]
    print()
    if all(results):
        print("=> 全部通过")
        return 0
    print("=> 有项目未通过，见上")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
