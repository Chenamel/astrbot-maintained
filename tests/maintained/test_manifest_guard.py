"""Guards for the protected-file manifest.

Two invariants are checked here:

1. This repository's working tree matches ``maintained/installed_manifest.json``
   -- the single source of truth for the maintained core. Editing a core file
   without refreshing its hash fails immediately instead of surfacing later as
   instance drift.
2. The manifest itself keeps its contract: core files only, no plugin or
   dashboard entries, and the proactive-reply switch marked as permanently
   disabled.
"""

import json
from pathlib import Path

from tools import check_drift

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "maintained" / "installed_manifest.json"

#: Number of protected files. Adding or removing entries requires updating this
#: pin in the same commit -- that is the point of the pin.
EXPECTED_ENTRY_COUNT = 31


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


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
