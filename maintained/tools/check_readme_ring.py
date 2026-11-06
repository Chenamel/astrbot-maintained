"""Validate the seven-file README language ring.

Changing the homepage means changing all seven files, but nothing in CI
checked that. A single-language edit could leave the ring asymmetric, or let
one translation drift away from the technical facts without anyone noticing.
This module is shared by the release gate and the maintained test suite.

Usage::

    python maintained/tools/check_readme_ring.py [repository-root]
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

FILES: tuple[str, ...] = (
    "README.md",
    "README_zh.md",
    "README_zh-TW.md",
    "README_ja.md",
    "README_fr.md",
    "README_es.md",
    "README_ru.md",
)

#: Display names from the upstream language bar, in file order.
LABELS: dict[str, str] = {
    "README.md": "English",
    "README_zh.md": "简体中文",
    "README_zh-TW.md": "繁體中文",
    "README_ja.md": "日本語",
    "README_fr.md": "Français",
    "README_es.md": "Español",
    "README_ru.md": "Русский",
}

_LANG_BAR_LINES = 12
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_URL = re.compile(r"https?://[^\s)`]+")
_NUMBER = re.compile(r"(?<![`\w])\d+(?:\.\d+)*(?![\w`])")
_MD_LINK = re.compile(r"\]\(([^)]+)\)")
_HREF = re.compile(r'href="([^"]+)"')
_HEADING = re.compile(r"^#{1,6} ", re.M)


@dataclass
class RingReport:
    """Collected problems; empty means the ring is consistent."""

    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when no problem was recorded."""
        return not self.problems

    def add(self, problem: str) -> None:
        """Record one problem."""
        self.problems.append(problem)

    def summary(self) -> str:
        """One-line verdict plus the first few problems."""
        if self.ok:
            return (
                f"{len(FILES)} README files: structure, facts and language bar in sync"
            )
        return f"{len(self.problems)} problem(s): " + "; ".join(self.problems[:4])


def _structure(text: str) -> tuple[int, int, int, int, int]:
    """Rows, headings, fenced blocks, table rows and markdown links."""
    lines = text.splitlines()
    return (
        len(lines),
        len(_HEADING.findall(text)),
        text.count("```") // 2,
        sum(line.startswith("|") for line in lines),
        len(_MD_LINK.findall(text)),
    )


def _facts(text: str) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """Inline code, URLs and numbers -- what translation must never change."""
    return (
        frozenset(_INLINE_CODE.findall(text)),
        frozenset(_URL.findall(text)),
        frozenset(_NUMBER.findall(text)),
    )


def _language_bar(text: str) -> tuple[list[str], str]:
    """Markdown-file hrefs in the header, plus the header itself."""
    head = "\n".join(text.splitlines()[:_LANG_BAR_LINES])
    return [href for href in _HREF.findall(head) if href.endswith(".md")], head


def check_ring(root: Path) -> RingReport:
    """Return a report on the seven README files under ``root``."""
    report = RingReport()
    present = {name: root / name for name in FILES if (root / name).is_file()}
    for name in FILES:
        if name not in present:
            report.add(f"missing {name}")

    base_path = present.get("README.md")
    if base_path is None:
        return report
    base_text = base_path.read_text(encoding="utf-8")
    base_struct = _structure(base_text)
    base_facts = _facts(base_text)

    for name, path in present.items():
        text = path.read_text(encoding="utf-8")
        if _structure(text) != base_struct:
            report.add(f"{name}: structure differs from README.md")
        if _facts(text) != base_facts:
            report.add(f"{name}: code/URL/number set differs from README.md")

        links, head = _language_bar(text)
        targets = [href.removeprefix("./") for href in links]
        expected = sorted(item for item in FILES if item != name)
        if sorted(targets) != expected:
            report.add(f"{name}: language bar must link the other 6 files")
        if any(href.startswith("http") for href in links):
            report.add(f"{name}: language bar must use relative links")
        if LABELS[name] not in head:
            report.add(f"{name}: own language label missing from the bar")
        if "AstrBotDevs/AstrBot/blob" in head:
            report.add(f"{name}: language bar points back at upstream")

        for href in _MD_LINK.findall(text):
            if href.startswith(("http", "#")):
                continue
            if not (root / href.removeprefix("./")).exists():
                report.add(f"{name}: broken relative link {href}")
    return report


def main(argv: list[str] | None = None) -> int:
    """Print the verdict; exit 1 when the ring is broken."""
    args = sys.argv[1:] if argv is None else argv
    root = Path(args[0]) if args else Path(__file__).resolve().parents[2]
    report = check_ring(root)
    print(report.summary())
    for problem in report.problems:
        print(f"  - {problem}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
