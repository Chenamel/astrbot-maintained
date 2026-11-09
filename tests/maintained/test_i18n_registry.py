"""Guard the fork's i18n namespace registration against upstream loader migrations.

Upstream 4.29.4 replaced the static ``translations.ts`` with per-locale
``locales/<lang>/index.ts`` bundles. A fork-only feature bundle that is present
on disk but not imported (or imported but not mounted) renders as
``[MISSING: ...]`` at runtime while the build still succeeds.
"""

from __future__ import annotations

import pathlib
import re

import pytest

LOCALES_ROOT = (
    pathlib.Path(__file__).resolve().parents[2]
    / "dashboard"
    / "src"
    / "i18n"
    / "locales"
)
LOCALES = ("zh-CN", "en-US", "ja-JP", "ru-RU")
IMPORT_RE = re.compile(r"import\s+(\w+)\s+from\s+'\./(features/[^']+\.json)'")


@pytest.mark.parametrize("locale", LOCALES)
def test_every_feature_bundle_is_imported(locale: str) -> None:
    """Every feature JSON on disk must be imported by that locale's index.ts."""
    base = LOCALES_ROOT / locale
    index = (base / "index.ts").read_text(encoding="utf-8")
    imported = {path for _, path in IMPORT_RE.findall(index)}
    on_disk = {
        path.relative_to(base).as_posix()
        for path in (base / "features").rglob("*.json")
    }

    assert on_disk == imported, (
        f"{locale}: unregistered bundles={sorted(on_disk - imported)}, "
        f"dangling imports={sorted(imported - on_disk)}"
    )


@pytest.mark.parametrize("locale", LOCALES)
def test_every_imported_bundle_is_mounted(locale: str) -> None:
    """An imported bundle that is not mounted cannot be resolved at runtime."""
    index = (LOCALES_ROOT / locale / "index.ts").read_text(encoding="utf-8")
    for variable, path in IMPORT_RE.findall(index):
        assert index.count(variable) >= 2, (
            f"{locale}: {path} imported as {variable} but never mounted"
        )
