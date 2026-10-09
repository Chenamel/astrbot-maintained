"""Guards the "additive only" rule for the public API surface.

The fork may add modules under ``astrbot/api/`` but must never modify the
upstream ones, because plugins depend on that surface. The baseline tag is
immutable, so it is the natural reference point: anything reported by
``git diff`` that is not on the allow-list below is a contract break.
"""

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

BASELINE = "baseline/v4.28.2"

#: Modules this fork added under astrbot/api/. Everything else must be
#: byte-identical to the baseline.
ALLOWED_ADDITIONS = {
    "astrbot/api/_bridge.py",
    "astrbot/api/content/__init__.py",
    "astrbot/api/delivery/__init__.py",
    "astrbot/api/embedding/__init__.py",
    "astrbot/api/media/__init__.py",
    "astrbot/api/permissions/__init__.py",
    "astrbot/api/proactive/__init__.py",
    "astrbot/api/runtime/__init__.py",
    "astrbot/api/turns/__init__.py",
}


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )


def _changed_under_api() -> set[str]:
    result = _git("diff", "--name-only", BASELINE, "--", "astrbot/api")
    assert result.returncode == 0, result.stderr
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def test_baseline_tag_is_available():
    if _git("rev-parse", "--verify", BASELINE).returncode != 0:
        pytest.skip(f"{BASELINE} is unavailable; cannot verify the frozen surface")


def test_upstream_api_files_are_untouched():
    unexpected = sorted(_changed_under_api() - ALLOWED_ADDITIONS)
    assert not unexpected, (
        "upstream astrbot/api files must not be modified, renamed or deleted: "
        f"{unexpected}"
    )


def test_allow_list_entries_all_exist_and_are_additions():
    changed = _changed_under_api()
    for path in sorted(ALLOWED_ADDITIONS):
        assert (REPO_ROOT / path).is_file(), f"allow-listed file is missing: {path}"
        if _git("rev-parse", "--verify", BASELINE).returncode == 0:
            assert path in changed, f"allow-listed file is not a baseline addition: {path}"
