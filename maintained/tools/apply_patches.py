"""Restore the maintained core into an AstrBot instance.

Sources the maintained core from this repository's working tree and copies the
files listed in ``maintained/installed_manifest.json`` into an AstrBot core
directory. Only manifest-listed files are ever touched.

The tool is dry-run by default; pass ``--apply`` to actually write files. Before
writing anything it backs the affected files up under
``<instance>/optimization_backups/<timestamp>_CST_apply_patches/``.

Usage::

    python maintained/tools/apply_patches.py --instance <instance dir>
    python maintained/tools/apply_patches.py --instance <dir> --apply

Exit codes:
    0 -- applied (or nothing to do)
    1 -- verification failed after applying
    2 -- usage error, or the source tree does not match the manifest

See ``docs/maintained/tools.md`` for the operational procedure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):  # run directly: python maintained/tools/apply_patches.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.check_drift import (  # noqa: E402
    DEFAULT_MANIFEST,
    REPO_ROOT,
    compare,
    load_manifest,
    resolve_core,
    sha256_of,
)

__all__ = ["Change", "backup_files", "build_plan", "main", "verify_source"]

ACTION_CREATE = "create"
ACTION_UPDATE = "update"
ACTION_SKIP = "skip"


@dataclass
class Change:
    """A planned change for one manifest entry.

    Attributes:
        relative: Repository-relative path.
        action: One of ``create``, ``update`` or ``skip``.
    """

    relative: str
    action: str

    @property
    def needs_write(self) -> bool:
        """Whether this change actually writes to the target tree."""
        return self.action in (ACTION_CREATE, ACTION_UPDATE)


def verify_source(source_root: Path, expected: dict[str, str]) -> list[str]:
    """Return manifest entries whose source file is missing or does not match.

    Args:
        source_root: Tree to read the maintained core from.
        expected: Mapping of relative path to expected SHA-256.

    Returns:
        A sorted list of offending relative paths; empty when the source is
        trustworthy.
    """
    broken = []
    for relative, digest in expected.items():
        candidate = source_root / relative
        if not candidate.is_file() or sha256_of(candidate) != digest:
            broken.append(relative)
    return sorted(broken)


def build_plan(target_core: Path, expected: dict[str, str]) -> list[Change]:
    """Decide what has to happen for each manifest entry.

    Args:
        target_core: Core directory to bring up to date.
        expected: Mapping of relative path to expected SHA-256.

    Returns:
        One :class:`Change` per manifest entry, sorted by path.
    """
    plan: list[Change] = []
    for relative, digest in sorted(expected.items()):
        target = target_core / relative
        if not target.is_file():
            action = ACTION_CREATE
        elif sha256_of(target) != digest:
            action = ACTION_UPDATE
        else:
            action = ACTION_SKIP
        plan.append(Change(relative=relative, action=action))
    return plan


def backup_files(
    changes: list[Change],
    target_core: Path,
    instance: Path,
) -> tuple[Path, list[dict[str, object]]]:
    """Copy every file that is about to be overwritten into a backup folder.

    Args:
        changes: The planned changes.
        target_core: Core directory that will be modified.
        instance: Instance root, used to place the backup folder.

    Returns:
        The backup directory and the recorded pre-state of each backed-up file.
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = instance / "optimization_backups" / f"{stamp}_CST_apply_patches"
    backup_dir.mkdir(parents=True, exist_ok=False)

    records: list[dict[str, object]] = []
    for change in changes:
        record: dict[str, object] = {
            "path": change.relative,
            "action": change.action,
            "state_before": "absent",
            "bytes": None,
            "sha256": None,
        }
        if change.action == ACTION_UPDATE:
            source = target_core / change.relative
            raw = source.read_bytes()
            record["state_before"] = "present"
            record["bytes"] = len(raw)
            record["sha256"] = sha256_of(source)
            destination = backup_dir / "core" / change.relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        records.append(record)
    return backup_dir, records


def _write_backup_notes(
    backup_dir: Path,
    records: list[dict[str, object]],
    instance: Path,
) -> None:
    """Write the backup receipt and restore notes."""
    payload = {
        "created_at": backup_dir.name,
        "kind": "apply_patches",
        "instance": str(instance),
        "note": "Only files listed in maintained/installed_manifest.json were touched.",
        "files": records,
    }
    (backup_dir / "manifest.json").write_bytes(
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    (backup_dir / "RESTORE.md").write_bytes(
        (
            "# Selective Recovery — apply_patches snapshot\n\n"
            "Restores the core files that `apply_patches.py` overwrote.\n\n"
            "1. Stop AstrBot.\n"
            "2. For every entry in `manifest.json`:\n"
            '   - `state_before: "present"` -> copy `core/<path>` back to\n'
            "     `<instance>/core/<path>`\n"
            '   - `state_before: "absent"` -> the file did not exist before; delete it\n'
            "     to roll back\n"
            "3. Restart AstrBot.\n\n"
            "`sha256` in `manifest.json` is the pre-change content hash.\n"
        ).encode()
    )


def _print_plan(plan: list[Change]) -> None:
    """Print the planned changes."""
    for change in plan:
        if change.action != ACTION_SKIP:
            print(f"  {change.action:6} {change.relative}")
    counts = {
        a: sum(1 for c in plan if c.action == a) for a in (ACTION_CREATE, ACTION_UPDATE)
    }
    skipped = sum(1 for c in plan if c.action == ACTION_SKIP)
    print(
        f"  => {counts[ACTION_CREATE]} to create, {counts[ACTION_UPDATE]} to update, {skipped} already ok"
    )


def write_build_stamp(instance: Path, source: Path, manifest_path: Path) -> Path | None:
    """Record which build a live instance is running.

    Args:
        instance: Instance root.
        source: Repository the files came from.
        manifest_path: Manifest that was applied.

    Returns:
        Path of the written stamp, or ``None`` when git metadata is unavailable.

    Notes:
        A deployed instance is a plain copy of files, so nothing on disk says
        where it came from. Recording the commit turns "is this the build I
        think it is" into a comparison instead of a memory exercise.
    """
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=source,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=source,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None

    try:
        version = subprocess.run(
            ["git", "show", f"{commit}:astrbot/__init__.py"],
            cwd=source,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        version = ""
    match = re.search(r'__version__\s*=\s*"([^"]+)"', version)

    payload = {
        "commit": commit,
        "branch": branch,
        "version": match.group(1) if match else "",
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "entries": len(load_manifest(manifest_path)),
        "applied_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    target = instance / "core" / "data" / "maintained_build.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    return target


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(
        description="Restore the maintained core into an AstrBot instance.",
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
        "--source",
        type=Path,
        default=REPO_ROOT,
        help="Tree to read the maintained core from (defaults to this repository).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write files. Without it the tool only prints the plan.",
    )
    args = parser.parse_args(argv)

    try:
        expected = load_manifest(args.manifest)
        target_core = resolve_core(args.instance)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    broken = verify_source(args.source, expected)
    if broken:
        print(
            "error: source tree does not match the manifest; aborting.", file=sys.stderr
        )
        for relative in broken:
            print(f"  {relative}", file=sys.stderr)
        return 2

    plan = build_plan(target_core, expected)
    pending = [change for change in plan if change.needs_write]

    print(f"source : {args.source}")
    print(f"target : {target_core}")
    if not pending:
        print("  => nothing to do; target already matches the manifest")
        # Files can match while the stamp is missing or stale -- a re-deploy of
        # an already-correct tree, or a checkout that moved on without touching
        # these files. Refreshing it here keeps the stamp honest instead of
        # leaving the gate comparing against a build that is merely older.
        if args.apply:
            stamp = write_build_stamp(args.instance, args.source, args.manifest)
            if stamp is not None:
                print(f"stamp  : {stamp}")
        return 0

    _print_plan(plan)

    if not args.apply:
        print("DRY RUN: nothing was written. Re-run with --apply to restore.")
        return 0

    backup_dir, records = backup_files(pending, target_core, args.instance)
    _write_backup_notes(backup_dir, records, args.instance)
    print(f"backup : {backup_dir}")

    for change in pending:
        source = args.source / change.relative
        destination = target_core / change.relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    report = compare(target_core, expected)
    counts = report.counts()
    print(
        f"verify : {report.total} entries -> {counts['ok']} ok, "
        f"{counts['mismatch']} mismatch, {counts['missing']} missing"
    )
    if not report.consistent:
        for relative in sorted(report.drift):
            print(f"  {report.entries[relative]:8} {relative}", file=sys.stderr)
        print("AstrBot must be restarted for changes to take effect.", file=sys.stderr)
        return 1

    stamp = write_build_stamp(args.instance, args.source, args.manifest)
    if stamp is not None:
        print(f"stamp  : {stamp}")

    print("AstrBot must be restarted for changes to take effect.")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via main()
    raise SystemExit(main())
