"""Guards for the protected-file manifest.

Three invariants are checked here:

1. This repository's working tree matches ``maintained/installed_manifest.json``
   -- the single source of truth for the maintained core. Editing a core file
   without refreshing its hash fails immediately instead of surfacing later as
   instance drift.
2. The manifest itself keeps its contract: core files only, no plugin or
   dashboard entries, and the proactive-reply switch marked as permanently
   disabled.
3. **Everything the fork touched is listed.** A file missing from the manifest
   is not deployed by ``apply_patches`` and is invisible to ``check_drift``, so
   the instance quietly runs without it. That is how four builtin-plugin assets
   were being copied by hand without anyone noticing.
"""

import json
import subprocess
from pathlib import Path

from tools import check_drift

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "maintained" / "installed_manifest.json"

#: Number of protected files. Adding or removing entries requires updating this
#: pin in the same commit -- that is the point of the pin.
#: 60 = 56 (core code) + 4 builtin-plugin assets (schema + metadata for
#: ``bot_info`` and ``tool_react``), which ``apply_patches`` also has to ship.
EXPECTED_ENTRY_COUNT = 60


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _base_ref() -> str:
    """Return the upstream reference the fork's changes are measured against."""
    return str(_manifest().get("base_ref") or "baseline/v4.28.2")


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, (
        f"git {' '.join(args)} failed: {result.stderr.strip() or 'unknown error'}"
    )
    return result.stdout


def test_repo_tree_matches_manifest():
    report = check_drift.compare(REPO_ROOT, check_drift.load_manifest(MANIFEST_PATH))
    assert report.consistent, f"working tree differs from manifest: {report.drift}"


def test_manifest_marks_proactive_as_permanently_disabled():
    assert _manifest()["proactive_must_remain_disabled"] is True


def test_manifest_entry_count_is_pinned():
    assert len(_manifest()["files"]) == EXPECTED_ENTRY_COUNT


def test_manifest_contains_core_files_only():
    files = _manifest()["files"]
    assert all(path.startswith("astrbot/") for path in files)
    assert not any("data/plugins" in path for path in files)
    assert not any(path.startswith("dashboard/") for path in files)


def test_manifest_hashes_are_lowercase_sha256():
    for path, digest in _manifest()["files"].items():
        assert len(digest) == 64, path
        assert digest == digest.lower(), path
        assert all(char in "0123456789abcdef" for char in digest), path


def test_every_touched_core_file_is_listed():
    """A core file the fork touched but did not list is silently undeployable.

    ``apply_patches`` only copies manifest entries and ``check_drift`` only
    compares manifest entries, so an unlisted file is invisible on both sides:
    it exists here and nowhere else. The four builtin-plugin assets were exactly
    this -- present on the development machine because someone copied them by
    hand, absent on any fresh instance.

    The comparison is against ``base_ref`` rather than the previous commit: what
    matters is "this fork changed it", not "the last patch touched it".
    """
    base = _base_ref()
    changed = {
        line.strip()
        for line in _git(
            "diff", "--name-only", f"{base}..HEAD", "--", "astrbot/"
        ).splitlines()
        if line.strip()
    }

    missing = sorted(changed - set(_manifest()["files"]))

    assert not missing, (
        f"{len(missing)} 个文件本 fork 改动过但未登记，部署时会被漏掉：\n  "
        + "\n  ".join(missing)
        + "\n补登记时同步更新 test_manifest_guard.EXPECTED_ENTRY_COUNT。"
    )


def test_listed_files_are_only_deployed_when_they_exist():
    """The manifest may not point at a file that is not in the tree."""
    absent = sorted(
        path for path in _manifest()["files"] if not (REPO_ROOT / path).is_file()
    )

    assert not absent, "台账登记了不存在的文件：\n  " + "\n  ".join(absent)
