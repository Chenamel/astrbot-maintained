"""Regression tests for the replay context-window fix (Gemini audit P0-5)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "maintained/proactive/replay.py"


def test_replay_walks_candidates_newest_first():
    """The judged message must be the newest row; ascending order deletes later candidates."""
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "for row in reversed(picked):" in source
    # Guard against reintroducing the ascending loop that wiped the window.
    assert "for row in picked:\n        trim_after(scratch, row.id)" not in source


def test_trim_after_keeps_earlier_candidates_when_walking_backwards():
    """Pure-SQL demo of the invariant the replay loop relies on."""
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    con.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(1, 6)])
    con.commit()
    candidates = [1, 3, 5]  # sampled, ascending as picked used to be

    # Correct (newest-first): each trim only removes rows newer than an
    # already-judged message, so earlier candidates survive.
    for row_id in reversed(candidates):
        con.execute("DELETE FROM t WHERE id > ?", (row_id,))
        con.commit()
        assert con.execute("SELECT id FROM t WHERE id = ?", (row_id,)).fetchone()
    assert con.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1
    con.close()
