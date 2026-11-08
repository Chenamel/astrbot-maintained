"""The built dashboard has to announce which version it is.

The core compares ``dist/assets/version`` against its own version before it
serves the assets. Upstream writes that file in its release pipeline, so a local
``vite build`` produces a dist without it; the core then calls perfectly good
assets incompatible and every start-up tries to download a package that does not
exist:

    Failed to download file from ... host='astrbot-registry.soulter.top' ... 404
    Failed to download file from ... host='github.com'
        file='AstrBot-4.29.4+mtn1-dashboard.zip' 404

The dashboard still worked, because it falls back to the local copy -- which is
why this went unnoticed while the log collected two errors per boot. These tests
fail if the stamp is missing or stale, so the fallback cannot become the normal
path again.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DIST = REPO_ROOT / "dashboard" / "dist"
VERSION_FILE = DIST / "assets" / "version"
STAMP_SCRIPT = REPO_ROOT / "scripts" / "stamp_dashboard_version.py"


def _core_version() -> str:
    """Read ``__version__`` from the package without importing it."""
    text = (REPO_ROOT / "astrbot" / "__init__.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("__version__"):
            return line.partition("=")[2].strip().strip("\"'")
    raise AssertionError("astrbot/__init__.py has no __version__")


def test_the_dist_carries_a_version_stamp():
    """Without this file the core treats the assets as foreign and re-downloads."""
    if not DIST.is_dir():
        pytest.skip("dashboard has not been built in this checkout")

    assert VERSION_FILE.is_file(), (
        f"missing {VERSION_FILE.relative_to(REPO_ROOT)}; run "
        "`python scripts/stamp_dashboard_version.py` after building the dashboard"
    )


def test_the_stamp_matches_the_running_version():
    """A stale stamp is the same problem one release later: it starts a download."""
    if not VERSION_FILE.is_file():
        pytest.skip("no stamp to compare")

    stamped = VERSION_FILE.read_text(encoding="utf-8").strip()
    expected = f"v{_core_version()}"

    assert stamped in (expected, expected[1:]), (
        f"dist is stamped {stamped!r}, core is {expected!r}; "
        "re-run scripts/stamp_dashboard_version.py"
    )


def test_the_core_accepts_the_local_dist():
    """The real predicate, not a string comparison: this is what the boot path asks."""
    if not VERSION_FILE.is_file():
        pytest.skip("no stamp to test")

    from astrbot import __version__
    from astrbot.core.dashboard_assets import _is_dist_compatible

    assert _is_dist_compatible(DIST, __version__), (
        "the core does not consider the local dashboard compatible, so it will "
        "try (and fail) to download one on every start-up"
    )


def test_the_stamp_script_agrees_with_the_committed_file():
    """The generator and the artifact must not drift apart."""
    if not VERSION_FILE.is_file():
        pytest.skip("no stamp to check")

    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(STAMP_SCRIPT), "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPO_ROOT,
    )

    assert result.returncode == 0, (
        f"stamp script reports a problem: {result.stderr.strip() or result.stdout.strip()}"
    )
