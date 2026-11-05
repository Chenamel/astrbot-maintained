"""Tests for the read-only memory sampler."""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path

from tools import mem_sample
from tools.mem_sample import (
    FIELDS,
    _print_delta,
    _report,
    _rows,
    read_judgements,
)


def _write_log(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_read_judgements_skips_replay_and_counts_recent(
    tmp_path: Path, monkeypatch
) -> None:
    # The log lives under whatever plugin the operator configured; the tool
    # takes it from ASTRBOT_CHECK_PLUGIN, so name one here rather than
    # depending on whatever the developer's environment happens to be.
    monkeypatch.setenv("ASTRBOT_CHECK_PLUGIN", "sample_plugin")
    monkeypatch.setattr(
        mem_sample,
        "SHADOW_LOG",
        "core/data/plugins/sample_plugin/shadow_log.jsonl",
    )
    log = tmp_path / mem_sample.SHADOW_LOG
    fresh = time.strftime("%Y-%m-%d %H:%M:%S")
    old = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 7200))
    _write_log(
        log,
        [
            {"source": "live", "ts": fresh},
            {"source": "live", "ts": fresh},
            {"source": "replay", "ts": fresh},
            {"source": "live", "ts": old},
        ],
    )
    total, recent = read_judgements(tmp_path)
    assert total == 3
    assert recent == 2


def test_read_judgements_missing_file(tmp_path: Path) -> None:
    assert read_judgements(tmp_path) == (0, 0)


def test_rows_and_report(tmp_path: Path) -> None:
    csv_path = tmp_path / "mem_samples.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow(
            {
                **{f: "" for f in FIELDS},
                "unix_ts": 1000,
                "local_time": "t0",
                "working_set_mb": 600,
                "private_mb": 3000,
                "judgements_total": 1,
            }
        )
        writer.writerow(
            {
                **{f: "" for f in FIELDS},
                "unix_ts": 1000 + 3600 * 2,
                "local_time": "t1",
                "working_set_mb": 700,
                "private_mb": 3100,
                "judgements_total": 2,
            }
        )
    rows = _rows(csv_path)
    assert len(rows) == 2
    assert _report(csv_path) == 0
    # The slope line is printed by both helpers; ensure it does not raise.
    _print_delta(csv_path)
