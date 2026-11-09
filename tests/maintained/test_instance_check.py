"""The plugin restart review scans rotated logs and respects both bounds."""

from __future__ import annotations

import sqlite3

from tools import instance_check


def _line(stamp: str, text: str) -> str:
    return f"[{stamp}] [Core] [ERRO] [v4.29.4+mtn1] [module:1]: {text}\n"


def _instance(tmp_path, *, log_files=None, plugin: str = ""):
    logdir = tmp_path / "core/data/logs"
    logdir.mkdir(parents=True)
    for name, content in (log_files or {"astrbot.log": ""}).items():
        (logdir / name).write_text(content, encoding="utf-8")
    con = sqlite3.connect(tmp_path / "core/data/data_v4.db")
    con.execute("CREATE TABLE preferences (key VARCHAR, value VARCHAR)")
    con.commit()
    con.close()
    if plugin:
        plugdir = tmp_path / f"core/data/plugins/{plugin}"
        plugdir.mkdir(parents=True)
        (plugdir / "shadow_log.jsonl").write_text(
            '{"ts": "2026-11-06 12:00:00", "decision": "SKIP"}\n',
            encoding="utf-8",
        )
        cfgdir = tmp_path / "core/data/config"
        cfgdir.mkdir(parents=True)
        (cfgdir / f"{plugin}_config.json").write_text(
            '{"live_groups": []}', encoding="utf-8"
        )
    return tmp_path


def test_rotated_logs_are_scanned_and_both_bounds_apply(capsys, tmp_path):
    root = _instance(
        tmp_path,
        log_files={
            "astrbot.2026-11-05_21-00-00_000000.log": (
                _line("2026-11-05 23:59:00", "before window")
                + _line("2026-11-06 02:00:00", "inside window")
            ),
            "astrbot.log": _line("2026-11-07 00:01:00", "next day"),
        },
    )

    ok = instance_check.check_log(root, "2026-11-06 00:00:00", "2026-11-07 00:00:00")
    out = capsys.readouterr().out

    assert ok is False
    assert "1 条" in out
    assert "inside window" in out
    assert "next day" not in out


def test_without_an_upper_bound_the_next_day_is_not_excluded(capsys, tmp_path):
    root = _instance(
        tmp_path,
        log_files={"astrbot.log": _line("2026-11-07 00:01:00", "next day")},
    )

    ok = instance_check.check_log(root, "2026-11-06 00:00:00")

    assert ok is False
    assert "next day" in capsys.readouterr().out


def test_no_plugin_skips_instead_of_reporting_a_false_failure(capsys, tmp_path):
    root = _instance(tmp_path)

    assert instance_check.check_files(root) is True
    assert instance_check.check_decisions(root) is True
    out = capsys.readouterr().out

    assert "跳过插件目录与配置检查" in out
    assert "跳过判定日志检查" in out
    assert "[FAIL]" not in out


def test_explicit_plugin_is_checked(capsys, tmp_path):
    root = _instance(tmp_path, plugin="sample_plugin")

    assert instance_check.check_files(root, "sample_plugin")
    assert instance_check.check_decisions(root, "sample_plugin")
    assert "shadow_log.jsonl" not in capsys.readouterr().out


def test_main_wires_the_new_arguments(tmp_path):
    root = _instance(
        tmp_path,
        log_files={"astrbot.log": ""},
        plugin="sample_plugin",
    )

    code = instance_check.main(
        [
            "--instance",
            str(root),
            "--plugin",
            "sample_plugin",
            "--since",
            "2026-11-06 00:00",
            "--until",
            "2026-11-07 00:00",
        ]
    )

    assert code == 0
