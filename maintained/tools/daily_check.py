"""Deterministic daily report for the maintained fork's live instance.

The morning automation used to ask a model to read log files, a JSONL stream
and a SQLite table by hand. Figures then drifted whenever a field disappeared,
a timestamp turned out to be UTC, or a rotated log was missed. This module
owns those decisions instead: it scans the full local-time window, classifies
errors and prints a fixed report. The automation only presents the output.

This is deliberately read-only. Usage::

    python maintained/tools/daily_check.py --instance "<instance dir>"
    python maintained/tools/daily_check.py --instance "<instance dir>" --date 2026-11-06
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path

#: The instance and its logs use GMT+8; ``provider_stats.created_at`` is UTC.
LOCAL_UTC_OFFSET = timedelta(hours=8)
FOCUS_GROUP_DEFAULT = "1105248343"
INCIDENT_GAP_MINUTES = 240
NOTICE_GAP_MINUTES = 60
NOISE_LIMIT = 50
ERROR_RATE_LIMIT = 0.10

LOG_DIR = "core/data/logs"
LOG_GLOB = "astrbot*.log"
SHADOW_LOG = "core/data/plugins/astrbot_plugin_proactive_shadow/shadow_log.jsonl"
DB_PATH = "core/data/data_v4.db"

STAMP_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
ERROR_RE = re.compile(r"\[(?:ERRO|CRIT)\]")
INCIDENT_RE = re.compile(
    r"database disk image is malformed|sqlite3\.DatabaseError|数据库查询出错"
    r"|PluginVersionUnsupportedError|Failed to load plugin|加载插件.*失败"
    r"|KeyError: 'items'",
    re.I,
)
NOISE_RE = re.compile(
    r"Failed to download file from https URL|获取 @ 用户信息失败"
    r"|InternalServerError|\b(?:429|502|503)\b|timeout|timed out"
    r"|asyncio\.run\(\) shutdown|unhandled exception during asyncio",
    re.I,
)


def _window(day: date) -> tuple[datetime, datetime, datetime, datetime]:
    """Return the local window and its naive-UTC equivalent.

    Args:
        day: Local calendar day to report.

    Returns:
        Local start/end (half-open), then UTC start/end for the same instant.
    """
    start = datetime.combine(day, time.min)
    end = start + timedelta(days=1)
    return start, end, start - LOCAL_UTC_OFFSET, end - LOCAL_UTC_OFFSET


def _scan_logs(
    root: Path, start: datetime, end: datetime
) -> tuple[list[datetime], list[str]]:
    """Scan every current and rotated log for lines inside the window.

    Args:
        root: Instance root directory.
        start: Inclusive local start.
        end: Exclusive local end.

    Returns:
        Sorted distinct timestamps and the matching error lines.
    """
    stamps: set[datetime] = set()
    errors: list[str] = []
    for path in sorted((root / LOG_DIR).glob(LOG_GLOB)):
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                match = STAMP_RE.match(line)
                if not match:
                    continue
                try:
                    stamp = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
                if not (start <= stamp < end):
                    continue
                stamps.add(stamp)
                if ERROR_RE.search(line):
                    errors.append(line.rstrip())
    return sorted(stamps), errors


def _longest_gap(stamps: list[datetime], start: datetime, end: datetime) -> int:
    """Longest silence in minutes, counting the window edges.

    Args:
        stamps: Sorted timestamps inside the window.
        start: Inclusive local start.
        end: Exclusive local end.

    Returns:
        Minutes of the longest gap; a full day when there is no data.
    """
    if not stamps:
        return int((end - start).total_seconds() // 60)
    points = [start, *stamps, end]
    return max(
        int((later - earlier).total_seconds() // 60)
        for earlier, later in zip(points, points[1:])
    )


def _decisions(
    root: Path, start: datetime, end: datetime
) -> tuple[Counter[str], list[dict], Counter[str]]:
    """Read the shadow decision log inside the window.

    Args:
        root: Instance root directory.
        start: Inclusive local start.
        end: Exclusive local end.

    Returns:
        Decision counts, real-send rows and per-group counts. ``NO_JUDGE`` is
        throttling, not a failure, so it is counted but never treated as ERROR.
    """
    decisions: Counter[str] = Counter()
    sends: list[dict] = []
    groups: Counter[str] = Counter()
    path = root / SHADOW_LOG
    if not path.is_file():
        return decisions, sends, groups
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Older files carried a ``source`` field; replay rows were tests.
            if row.get("source") == "replay":
                continue
            try:
                stamp = datetime.strptime(
                    str(row.get("ts", ""))[:19], "%Y-%m-%d %H:%M:%S"
                )
            except ValueError:
                continue
            if not (start <= stamp < end):
                continue
            decisions[str(row.get("decision") or "UNKNOWN")] += 1
            group = str(row.get("group") or "").rsplit(":", 1)[-1]
            if group:
                groups[group] += 1
            if row.get("sent") is True:
                sends.append(
                    {
                        "group": group,
                        "text": str(row.get("persona_text") or "")[:60],
                    }
                )
    return decisions, sends, groups


def _cost(root: Path, utc_start: datetime, utc_end: datetime) -> dict:
    """Summarise provider usage over the UTC-equivalent window.

    Args:
        root: Instance root directory.
        utc_start: Inclusive naive-UTC start.
        utc_end: Exclusive naive-UTC end.

    Returns:
        Request total, input-other tokens and the two busiest agent types.
    """
    empty = {"requests": 0, "input_other": 0, "top": []}
    path = root / DB_PATH
    if not path.is_file():
        return empty
    try:
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5)
        rows = con.execute(
            "SELECT agent_type, COUNT(*), COALESCE(SUM(token_input_other), 0) "
            "FROM provider_stats WHERE created_at >= ? AND created_at < ? "
            "GROUP BY agent_type ORDER BY COUNT(*) DESC",
            (
                utc_start.strftime("%Y-%m-%d %H:%M:%S"),
                utc_end.strftime("%Y-%m-%d %H:%M:%S"),
            ),
        ).fetchall()
        con.close()
    except sqlite3.Error:
        return empty
    return {
        "requests": sum(row[1] for row in rows),
        "input_other": sum(int(row[2] or 0) for row in rows),
        "top": [
            {
                "agent": row[0],
                "requests": row[1],
                "input_other": int(row[2] or 0),
            }
            for row in rows[:2]
        ],
    }


def collect_report(
    root: Path,
    day: date,
    focus_group: str = FOCUS_GROUP_DEFAULT,
    now: datetime | None = None,
) -> dict:
    """Collect every figure the morning report needs.

    Args:
        root: Instance root directory (the one containing ``core/``).
        day: Local calendar day to report.
        focus_group: Group whose real sends deserve an excerpt.
        now: Clock value for tests; defaults to the current local time.

    Returns:
        Structured report; ``level`` is ``ok``, ``notice`` or ``incident``.
    """
    start, end, utc_start, utc_end = _window(day)
    stamps, errors = _scan_logs(root, start, end)
    # When the report covers today, the rest of the day has not happened yet;
    # counting it as silence would invent a fake outage every morning.
    effective_end = max(start, min(end, now or datetime.now()))
    incident_lines = [line for line in errors if INCIDENT_RE.search(line)]
    noise_lines = [
        line
        for line in errors
        if not INCIDENT_RE.search(line) and NOISE_RE.search(line)
    ]
    other_lines = [
        line
        for line in errors
        if not INCIDENT_RE.search(line) and not NOISE_RE.search(line)
    ]

    decisions, sends, groups = _decisions(root, start, end)
    cost = _cost(root, utc_start, utc_end)
    total = sum(decisions.values())
    error_rate = decisions.get("ERROR", 0) / total if total else 0.0
    gap = _longest_gap(stamps, start, effective_end)

    reasons: list[str] = []
    level = "ok"
    if incident_lines:
        level = "incident"
        reasons.append(f"事故级错误 {len(incident_lines)} 条")
    if not stamps and effective_end > start:
        level = "incident"
        reasons.append("全天无日志（疑似停机）")
    elif gap > INCIDENT_GAP_MINUTES:
        level = "incident"
        reasons.append(f"日志静默 {gap // 60}h{gap % 60}m")
    elif gap > NOTICE_GAP_MINUTES and level == "ok":
        level = "notice"
        reasons.append(f"日志静默 {gap} 分钟")
    if error_rate > ERROR_RATE_LIMIT:
        level = "incident"
        reasons.append(f"判定 ERROR {error_rate:.1%}")
    if len(noise_lines) + len(other_lines) > NOISE_LIMIT and level == "ok":
        level = "notice"
        reasons.append(f"外部噪声 {len(noise_lines) + len(other_lines)} 条")

    focus_sends = [row for row in sends if row["group"] == focus_group]
    return {
        "day": str(day),
        "level": level,
        "reasons": reasons,
        "gap_minutes": gap,
        "errors": {
            "total": len(errors),
            "incident": len(incident_lines),
            "noise": len(noise_lines),
            "other": len(other_lines),
        },
        "decisions": dict(decisions),
        "sent_total": len(sends),
        "focus_group": focus_group,
        "focus_sends": focus_sends,
        "top_groups": groups.most_common(3),
        "cost": cost,
        "watch": [line[:100] for line in other_lines[:2]],
    }


def format_report(report: dict) -> str:
    """Render the fixed seven-line morning report.

    Args:
        report: Output of :func:`collect_report`.

    Returns:
        Markdown list with no more than eight lines.
    """
    mark = {"ok": "通过", "notice": "注意", "incident": "⚠️ 异常"}[report["level"]]
    reasons = "；".join(report["reasons"]) or "无"
    decisions = report["decisions"]
    total = sum(decisions.values())
    errors = decisions.get("ERROR", 0)
    rate = f"{errors / total:.2%}" if total else "—"
    focus = report["focus_sends"]
    excerpt = f"（{focus[0]['text']}）" if focus and focus[0]["text"] else ""
    groups = " / ".join(f"{group} {count}" for group, count in report["top_groups"])
    top = "、".join(
        f"{row['agent']} {row['requests']}" for row in report["cost"]["top"]
    )
    lines = [
        f"- 健康：{mark}（{reasons}）",
        f"- 日志：ERRO {report['errors']['total']}"
        f"（事故 {report['errors']['incident']} / 噪声 {report['errors']['noise']}"
        f" / 其他 {report['errors']['other']}）；最长静默 {report['gap_minutes']} 分钟",
        f"- 判定：{total} / REPLY {decisions.get('REPLY', 0)}"
        f" / 真发送 {report['sent_total']} / ERROR {errors}（{rate}）",
        f"- 重点群 {report['focus_group']}：{len(focus)} 条{excerpt}",
        f"- 群 Top3：{groups or '无'}",
        f"- 成本：{report['cost']['requests']} 请求"
        f" / input_other {report['cost']['input_other'] / 10000:.1f} 万；{top or '无'}",
        f"- 需关注：{'; '.join(report['watch']) or '无'}",
    ]
    return "\n".join(lines[:8])


def main(argv: list[str] | None = None) -> int:
    """Print the report; a non-zero code only means the script could not run.

    Args:
        argv: Optional argument list for tests.

    Returns:
        0 when the report was produced, 2 for a bad instance directory.
    """
    parser = argparse.ArgumentParser(
        description="Read-only daily check for a live instance"
    )
    parser.add_argument("--instance", required=True, type=Path)
    parser.add_argument(
        "--date", default="", help="Local day YYYY-MM-DD; defaults to yesterday"
    )
    parser.add_argument("--focus-group", default=FOCUS_GROUP_DEFAULT)
    args = parser.parse_args(argv)
    root = args.instance
    if not (root / "core").is_dir():
        print(f"实例目录不含 core/: {root}", file=sys.stderr)
        return 2
    day = (
        datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date
        else (datetime.now() - timedelta(days=1)).date()
    )
    report = collect_report(root, day, args.focus_group)
    print(f"日期：{day}（本地 GMT+8；成本按等价 UTC 窗口）")
    print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
