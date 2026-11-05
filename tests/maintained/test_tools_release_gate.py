"""Tests for the bundled-dist stashing in maintained/tools/release_gate.py.

Upstream's suite assumes ``astrbot/dashboard/dist`` is absent: several tests
assert that a rejected WebUI directory resolves to ``None``, and the updater
tests branch differently once a bundled copy exists. A release build creates
that directory on purpose, so the gate moves it aside for the upstream run and
restores it afterwards.

The restore path matters more than the move: a failure there would delete a
build the maintainer just spent a minute producing. These tests pin both.
"""

from pathlib import Path

import pytest
from tools import release_gate


@pytest.fixture()
def fake_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the gate at a temporary repo root holding a bundled dist."""
    dist = tmp_path / "astrbot" / "dashboard" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    (dist / "assets" / "version").write_text("v1.0.0\n", encoding="utf-8")
    monkeypatch.setattr(release_gate, "REPO_ROOT", tmp_path)
    return dist


def test_dist_is_absent_while_upstream_runs(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run must not see a bundled dist, or upstream's own tests fail."""
    seen: list[bool] = []

    def fake_run(cmd, timeout=None):
        seen.append(fake_repo.is_dir())
        return 0, "2949 passed, 6 skipped, 2 xfailed in 1.0s"

    monkeypatch.setattr(release_gate, "_run", fake_run)
    monkeypatch.setattr(release_gate, "expected_deviations", lambda: 2)

    status, detail, counts = release_gate.gate_upstream()

    assert seen == [False], "the bundled dist was still visible to pytest"
    assert status == release_gate.PASS, detail
    assert counts["passed"] == 2949


def test_dist_is_restored_after_a_failing_run(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A red upstream run must still leave the build where it was."""

    def fake_run(cmd, timeout=None):
        return 1, "6 failed, 2942 passed"

    monkeypatch.setattr(release_gate, "_run", fake_run)
    monkeypatch.setattr(release_gate, "expected_deviations", lambda: 2)

    status, _, _ = release_gate.gate_upstream()

    assert status == release_gate.FAIL
    assert (fake_repo / "index.html").is_file(), "the build was not restored"
    assert (fake_repo / "assets" / "version").read_text(encoding="utf-8") == "v1.0.0\n"


def test_restore_survives_an_interrupted_run(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """KeyboardInterrupt must not take the build with it."""

    def fake_run(cmd, timeout=None):
        raise KeyboardInterrupt

    monkeypatch.setattr(release_gate, "_run", fake_run)

    with pytest.raises(KeyboardInterrupt):
        release_gate.gate_upstream()

    assert (fake_repo / "index.html").is_file(), "the build was not restored"


def test_no_dist_means_nothing_to_stash(tmp_path: Path, monkeypatch) -> None:
    """A clean checkout has no dist; the gate must not fail over its absence."""
    monkeypatch.setattr(release_gate, "REPO_ROOT", tmp_path)

    def fake_run(cmd, timeout=None):
        return 0, "2949 passed, 6 skipped, 2 xfailed in 1.0s"

    monkeypatch.setattr(release_gate, "_run", fake_run)
    monkeypatch.setattr(release_gate, "expected_deviations", lambda: 2)

    status, detail, _ = release_gate.gate_upstream()

    assert status == release_gate.PASS, detail
    assert not (tmp_path / "astrbot" / "dashboard" / "dist").exists()
