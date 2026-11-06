"""The seven README files must stay a symmetric, fact-identical ring."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from tools.check_readme_ring import FILES, check_ring

REPO_ROOT = Path(__file__).resolve().parents[2]


def _fixture(tmp_path: Path) -> Path:
    for name in FILES:
        shutil.copy2(REPO_ROOT / name, tmp_path / name)
    return tmp_path


def test_the_repository_ring_is_consistent() -> None:
    report = check_ring(REPO_ROOT)
    assert report.ok, report.summary()


def test_a_dropped_language_link_is_detected(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path = root / "README_ja.md"
    text = path.read_text(encoding="utf-8")
    broken = re.sub(r'href="\./README[^"]*\.md"', "", text, count=1)
    assert broken != text
    path.write_bytes(broken.encode("utf-8"))

    problems = check_ring(root).problems
    assert any("language bar" in p for p in problems)


def test_a_drifting_technical_number_is_detected(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path = root / "README_fr.md"
    text = path.read_text(encoding="utf-8")
    path.write_bytes(text.replace("4.28.2", "4.28.3", 1).encode("utf-8"))

    problems = check_ring(root).problems
    assert any("code/URL/number" in p for p in problems)


def test_a_missing_language_file_is_detected(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    (root / "README_ru.md").unlink()

    problems = check_ring(root).problems
    assert any("missing README_ru.md" in p for p in problems)


def test_an_upstream_language_link_is_detected(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path = root / "README_es.md"
    text = path.read_text(encoding="utf-8")
    broken = re.sub(
        r'href="\./README[^"]*\.md"',
        'href="https://github.com/AstrBotDevs/AstrBot/blob/master/README_fr.md"',
        text,
        count=1,
    )
    assert broken != text
    path.write_bytes(broken.encode("utf-8"))

    problems = check_ring(root).problems
    assert any("back at upstream" in p for p in problems)
    assert any("relative links" in p or "other 6 files" in p for p in problems)
