"""The daily report owns the window, field names, classes and UTC shift."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta

from tools import daily_check

DAY = date(2026, 11, 6)
FOCUS = "100000000"


def _line(stamp: str, text: str = "ordinary", level: str = "INFO") -> str:
    return f"[{stamp}] [Core] [{level}] [v4.28.2+mtn1] [module:1]: {text}\n"


def _background() -> str:
    """One INFO line every 30 minutes, so no silence rule fires."""
    start = datetime(2026, 11, 6)
    return "".join(
        _line((start + timedelta(minutes=30 * i)).strftime("%Y-%m-%d %H:%M:%S"))
        for i in range(48)
    )


def _instance(tmp_path, *, log_files=None, decisions=(), costs=()):
    logdir = tmp_path / "core/data/logs"
    logdir.mkdir(parents=True)
    for name, content in (log_files or {"astrbot.log": _background()}).items():
        (logdir / name).write_text(content, encoding="utf-8")
    shadow = tmp_path / "core/data/plugins/sample_plugin"
    shadow.mkdir(parents=True)
    (shadow / "shadow_log.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in decisions),
        encoding="utf-8",
    )
    con = sqlite3.connect(tmp_path / "core/data/data_v4.db")
    con.execute(
        "CREATE TABLE provider_stats "
        "(created_at DATETIME, agent_type VARCHAR, token_input_other INTEGER)"
    )
    con.executemany("INSERT INTO provider_stats VALUES (?, ?, ?)", costs)
    con.commit()
    con.close()
    return tmp_path


def _row(ts: str, decision: str = "SKIP", **extra) -> dict:
    row = {
        "ts": ts,
        "group": f"default:GroupMessage:{FOCUS}",
        "mode": "live",
        "decision": decision,
        "sent": False,
    }
    row.update(extra)
    return row


def test_rotated_logs_are_scanned_and_window_is_half_open(tmp_path) -> None:
    rotated = _line("2026-11-05 23:59:00", "old", "ERRO") + _line(
        "2026-11-06 02:00:00", "database disk image is malformed", "ERRO"
    )
    current = _line("2026-11-07 00:01:00", "today", "ERRO")
    root = _instance(
        tmp_path,
        log_files={
            "astrbot.2026-11-05_21-00-00_000000.log": rotated,
            "astrbot.log": _background() + current,
        },
    )

    report = daily_check.collect_report(root, DAY)

    assert report["errors"]["total"] == 1
    assert report["errors"]["incident"] == 1
    assert report["level"] == "incident"


def test_noise_alone_does_not_raise_an_incident(tmp_path) -> None:
    noise = "".join(
        _line(
            f"2026-11-06 03:0{i}:00",
            text,
            "ERRO",
        )
        for i, text in enumerate(
            [
                "Failed to download file from https URL host='gxh.vip.qq.com'",
                "获取 @ 用户信息失败: retcode 100",
                "unhandled exception during asyncio.run() shutdown",
            ]
        )
    )
    root = _instance(tmp_path, log_files={"astrbot.log": _background() + noise})

    report = daily_check.collect_report(root, DAY)

    assert report["errors"]["noise"] == 3
    assert report["level"] == "ok"


def test_incident_marker_is_reported_with_a_reason(tmp_path) -> None:
    line = _line("2026-11-06 04:00:00", "PluginVersionUnsupportedError", "ERRO")
    root = _instance(tmp_path, log_files={"astrbot.log": _background() + line})

    report = daily_check.collect_report(root, DAY)

    assert report["level"] == "incident"
    assert any("事故级错误" in reason for reason in report["reasons"])


def test_a_day_without_logs_is_an_incident(tmp_path) -> None:
    root = _instance(tmp_path, log_files={"astrbot.log": ""})

    report = daily_check.collect_report(root, DAY)

    assert report["level"] == "incident"
    assert any("全天无日志" in reason for reason in report["reasons"])


def test_error_rate_above_ten_percent_is_an_incident(tmp_path) -> None:
    decisions = [
        _row(f"2026-11-06 10:00:{i:02d}", "ERROR" if i < 2 else "SKIP")
        for i in range(10)
    ]
    root = _instance(tmp_path, decisions=decisions)

    report = daily_check.collect_report(root, DAY)

    assert report["decisions"]["ERROR"] == 2
    assert report["level"] == "incident"
    assert any("判定 ERROR" in reason for reason in report["reasons"])


def test_no_judge_is_throttling_not_a_failure(tmp_path) -> None:
    decisions = [
        _row(f"2026-11-06 10:00:{i:02d}", "NO_JUDGE", skipped_by="quota")
        for i in range(10)
    ]
    root = _instance(tmp_path, decisions=decisions)

    report = daily_check.collect_report(root, DAY)

    assert report["decisions"]["NO_JUDGE"] == 10
    assert report["level"] == "ok"


def test_cost_window_is_shifted_to_utc(tmp_path) -> None:
    costs = [
        ("2026-11-05 15:59:00", "internal", 999),  # before the window
        ("2026-11-05 16:01:00", "internal", 100),  # local 00:01 on DAY
        ("2026-11-06 16:01:00", "internal", 888),  # local 00:01 next day
    ]
    root = _instance(tmp_path, costs=costs)

    report = daily_check.collect_report(root, DAY)

    assert report["cost"]["requests"] == 1
    assert report["cost"]["input_other"] == 100


def test_report_is_compact_and_quotes_the_focus_group(tmp_path) -> None:
    decisions = [
        _row(
            "2026-11-06 12:00:00",
            "REPLY",
            sent=True,
            persona_text="这是一条有信息量的回复",
        )
    ]
    root = _instance(tmp_path, decisions=decisions)

    report = daily_check.collect_report(root, DAY, FOCUS)
    text = daily_check.format_report(report)

    assert len(text.splitlines()) <= 8
    assert f"重点群 {FOCUS}：1 条" in text
    assert "这是一条有信息量的回复" in text
    assert report["top_groups"] == [(FOCUS, 1)]


def test_a_partial_day_does_not_invent_a_future_outage(tmp_path) -> None:
    """Reporting today must stop the silence clock at the injected now."""
    noon = datetime(2026, 11, 6, 12, 0, 0)
    lines = "".join(
        _line(
            (datetime(2026, 11, 6) + timedelta(minutes=30 * i)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )
        for i in range(24)
    )
    root = _instance(tmp_path, log_files={"astrbot.log": lines})

    report = daily_check.collect_report(root, DAY, FOCUS, now=noon)

    assert report["gap_minutes"] <= 30
    assert not any("日志静默" in reason for reason in report["reasons"])
    assert report["level"] == "ok"


def test_known_plugin_noise_does_not_fill_the_watch_line(tmp_path) -> None:
    """A recurring plugin failure is noise, not a new thing to investigate."""
    line = _line(
        "2026-11-06 05:00:00",
        "[ContentSafetyGuard] LLM组合审查调用失败: connection reset",
        "ERRO",
    )
    root = _instance(tmp_path, log_files={"astrbot.log": _background() + line})

    report = daily_check.collect_report(root, DAY)

    assert report["errors"]["noise"] == 1
    assert report["watch"] == []
    assert report["level"] == "ok"
