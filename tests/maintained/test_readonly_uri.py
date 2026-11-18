"""Read-only SQLite URIs must be valid on Windows paths."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def test_replay_ro_uri_opens_real_database(tmp_path: Path):
    from proactive.replay import ro_uri

    db = tmp_path / "data_v4.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE t (a INTEGER)")
    con.commit()
    con.close()

    uri = ro_uri(db)
    assert uri.startswith("file:///") and uri.endswith("?mode=ro")
    ro = sqlite3.connect(uri, uri=True)
    assert ro.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0
    ro.close()


def test_daily_check_uses_resolved_uri():
    source = (
        Path(__file__).resolve().parents[2] / "maintained/tools/daily_check.py"
    ).read_text(encoding="utf-8")
    assert "path.resolve().as_uri()" in source
    assert "file:{path.as_posix()}" not in source
