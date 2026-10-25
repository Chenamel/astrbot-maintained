"""Detect drift between the maintained core and an AstrBot instance.

The maintained core is described by ``maintained/installed_manifest.json``
(relative paths mapped to SHA-256 of the file bytes on disk). This tool compares
a target tree against that manifest and reports every file that is missing or
has different content.

Usage::

    python maintained/tools/check_drift.py --instance <instance dir>
    python maintained/tools/check_drift.py --instance <dir> --json
    python maintained/tools/check_drift.py --instance <dir> --check-repo

Exit codes:
    0 -- no drift
    1 -- drift detected
    2 -- usage or environment error

See ``docs/maintained/tools.md`` for the operational procedure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["DriftReport", "compare", "main"]

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "maintained" / "installed_manifest.json"

STATUS_OK = "ok"
STATUS_MISMATCH = "mismatch"
STATUS_MISSING = "missing"


@dataclass
class DriftReport:
    """Result of comparing one tree against the manifest.

    Attributes:
        root: The tree that was inspected.
        entries: ``relative path -> status`` for every manifest entry.
        drift: The relative paths whose status is not ``ok``.
    """

    root: Path
    entries: dict[str, str] = field(default_factory=dict)
    drift: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Number of manifest entries inspected."""
        return len(self.entries)

    @property
    def consistent(self) -> bool:
        """Whether the tree matches the manifest completely."""
        return not self.drift

    def counts(self) -> dict[str, int]:
        """Return the number of entries per status."""
        result = {STATUS_OK: 0, STATUS_MISMATCH: 0, STATUS_MISSING: 0}
        for status in self.entries.values():
            result[status] = result.get(status, 0) + 1
        return result

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable view of the report."""
        return {
            "root": str(self.root),
            "total": self.total,
            "consistent": self.consistent,
            "counts": self.counts(),
            "drift": sorted(self.drift),
            "entries": dict(sorted(self.entries.items())),
        }


def load_manifest(manifest_path: Path) -> dict[str, str]:
    """Load the protected-file manifest.

    Args:
        manifest_path: Path to ``installed_manifest.json``.

    Returns:
        Mapping of relative path to expected SHA-256.

    Raises:
        FileNotFoundError: When the manifest does not exist.
        ValueError: When the manifest has no ``files`` mapping.
    """
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = data.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError(f"manifest has no usable 'files' mapping: {manifest_path}")
    return {str(k): str(v) for k, v in files.items()}


def sha256_of(path: Path) -> str:
    """Return the SHA-256 of a file's bytes on disk."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(root: Path, expected: dict[str, str]) -> DriftReport:
    """Compare a tree against expected hashes.

    Args:
        root: Directory that should contain the manifest files.
        expected: Mapping of relative path to expected SHA-256.

    Returns:
        A report describing every entry as ``ok``, ``mismatch`` or ``missing``.
    """
    report = DriftReport(root=root)
    for relative, digest in expected.items():
        target = root / relative
        if not target.is_file():
            status = STATUS_MISSING
        elif sha256_of(target) != digest:
            status = STATUS_MISMATCH
        else:
            status = STATUS_OK
        report.entries[relative] = status
        if status != STATUS_OK:
            report.drift.append(relative)
    return report


def resolve_core(instance: Path) -> Path:
    """Return the core directory of an AstrBot instance.

    Args:
        instance: Instance root, or the core directory itself.

    Returns:
        The directory that holds ``astrbot/``.

    Raises:
        FileNotFoundError: When no core directory can be located.
    """
    # Launcher-managed instances keep the package under core/, so that is the
    # real one. Checking a stray <instance>/astrbot first made the report look
    # clean while the running code was untouched.
    core = instance / "core"
    if (core / "astrbot").is_dir():
        return core
    if (instance / "astrbot").is_dir():
        return instance
    raise FileNotFoundError(f"no AstrBot core found under {instance}")


def _print_report(report: DriftReport, label: str) -> None:
    """Print a human-readable report."""
    counts = report.counts()
    print(f"[{label}] {report.root}")
    print(
        f"  {report.total} entries: "
        f"{counts[STATUS_OK]} ok, "
        f"{counts[STATUS_MISMATCH]} mismatch, "
        f"{counts[STATUS_MISSING]} missing"
    )
    for relative in sorted(report.drift):
        print(f"    {report.entries[relative]:8} {relative}")
    print(f"  => {'NO DRIFT' if report.consistent else 'DRIFT DETECTED'}")


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(
        description="Detect drift between the maintained core and an instance.",
    )
    parser.add_argument(
        "--instance",
        required=True,
        type=Path,
        help="AstrBot instance directory (or its core directory).",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Path to installed_manifest.json.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of text.",
    )
    parser.add_argument(
        "--check-repo",
        action="store_true",
        help="Also compare this repository's working tree against the manifest.",
    )
    args = parser.parse_args(argv)

    try:
        expected = load_manifest(args.manifest)
        core = resolve_core(args.instance)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    instance_report = compare(core, expected)
    repo_report = compare(REPO_ROOT, expected) if args.check_repo else None

    if args.json:
        payload: dict[str, object] = {"instance": instance_report.to_dict()}
        if repo_report is not None:
            payload["repo"] = repo_report.to_dict()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_report(instance_report, "instance")
        if repo_report is not None:
            _print_report(repo_report, "repo")

    drifted = not instance_report.consistent or (
        repo_report is not None and not repo_report.consistent
    )
    return 1 if drifted else 0


if __name__ == "__main__":  # pragma: no cover - exercised via main()
    raise SystemExit(main())
