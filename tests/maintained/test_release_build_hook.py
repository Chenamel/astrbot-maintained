"""The release build hook must describe what the wheel will actually contain.

``pyproject.toml`` ships ``astrbot/dashboard/dist/**`` as an artifact even when
the hook skips the npm rebuild. An unconditional "the wheel will contain no
WebUI" warning sends the release builder into a rebuild that is unnecessary at
best (and fails without Node at worst). Only a genuinely missing dist warrants
that warning.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_skipped_rebuild_distinguishes_an_existing_dist() -> None:
    text = (REPO_ROOT / "scripts" / "hatch_build.py").read_text(encoding="utf-8")

    assert "existing.is_dir()" in text
    assert "Reusing existing" in text
    # The warning must still exist for the case where nothing can be shipped.
    assert "the wheel will contain no WebUI" in text


def test_artifacts_declaration_is_what_makes_reuse_valid() -> None:
    """The message is only truthful while the dist is a declared artifact."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'artifacts = ["astrbot/dashboard/dist/**"]' in pyproject
