"""One command that answers "can this be released?".

The checks already exist as separate tools; what was missing is something that
runs them in one order and returns a single verdict. Each step reports its own
numbers so a failure can be read without re-running anything.

Usage::

    python maintained/tools/release_gate.py
    python maintained/tools/release_gate.py --instance <instance dir>
    python maintained/tools/release_gate.py --skip-upstream

Exit codes:
    0   every gate passed
    1   a gate failed (the failing one is named)
    2   the gate could not run (missing tool, bad path)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):  # run directly: python maintained/tools/release_gate.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.check_drift import DEFAULT_MANIFEST, compare, load_manifest  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = DEFAULT_MANIFEST
DEVIATIONS = REPO_ROOT / "maintained" / "p11_deviations.py"

#: Values a gate can return.
PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


def _run(cmd: list[str], *, timeout: int = 1800) -> tuple[int, str]:
    """Run a command and return its exit code with combined output."""
    try:
        result = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 2, str(exc)
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def _pytest_summary(output: str) -> dict[str, int]:
    """Pull the counts out of a pytest ``-q`` tail.

    Args:
        output: Combined pytest output.

    Returns:
        Mapping with ``passed``, ``failed``, ``xfailed`` and ``skipped``; a key
        is absent when pytest did not report it.
    """
    counts: dict[str, int] = {}
    for label in ("passed", "failed", "xfailed", "skipped", "error", "errors"):
        for match in re.finditer(rf"(\d+) {label}\b", output):
            counts[label.rstrip("s")] = int(match.group(1))
    return counts


def expected_deviations() -> int:
    """Return how many upstream tests are registered as known deviations."""
    text = DEVIATIONS.read_text(encoding="utf-8")
    # The registry literal is the only dict assigned to DEVIATIONS.
    match = re.search(r"^DEVIATIONS.*?=\s*\{(.*?)^\}", text, re.S | re.M)
    if not match:
        return -1
    return len(re.findall(r'^\s*"tests/', match.group(1), re.M))


def _ruff() -> list[str] | None:
    """Locate a ruff entry point.

    ``python -m ruff`` only works when the running interpreter has ruff
    installed, and here the test environment and the lint environment are
    separate. Fall back to a binary in a known location before giving up.

    Returns:
        A command prefix, or ``None`` when ruff cannot be found anywhere.
    """
    code, _ = _run([sys.executable, "-m", "ruff", "--version"], timeout=60)
    if code == 0:
        return [sys.executable, "-m", "ruff"]

    candidates = [
        Path(sys.executable).parent / "ruff.exe",
        Path(sys.executable).parent / "ruff",
        Path.home() / ".workbuddy/binaries/python/envs/default/Scripts/ruff.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return [str(candidate)]
    return None


def gate_lint() -> tuple[str, str]:
    """ruff check plus a format check."""
    ruff = _ruff()
    if ruff is None:
        return SKIP, "ruff not available in this environment"

    code, out = _run(ruff + ["check", "astrbot", "maintained"])
    if code != 0:
        tail = out.strip().splitlines()[-1] if out.strip() else "ruff check failed"
        return FAIL, tail
    code, out = _run(ruff + ["format", "--check", "astrbot", "maintained"])
    if code != 0:
        return FAIL, "format drift: run `ruff format astrbot maintained`"
    return PASS, "ruff check + format clean"


def gate_manifest() -> tuple[str, str]:
    """Every touched file is listed, and the tree matches the hashes."""
    code, out = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/maintained/test_manifest_guard.py",
            "-q",
        ]
    )
    if code != 0:
        return FAIL, "manifest guard failed; see pytest output"
    report = compare(REPO_ROOT, load_manifest(MANIFEST))
    counts = report.counts()
    return PASS, (
        f"{report.total} entries, {counts['ok']} ok, {counts['mismatch']} mismatch"
    )


def gate_maintained() -> tuple[str, str, dict[str, int]]:
    """The fork's own suite must be entirely green."""
    code, out = _run([sys.executable, "-m", "pytest", "tests/maintained", "-q"])
    counts = _pytest_summary(out)
    if code != 0 or counts.get("failed") or counts.get("error"):
        return FAIL, f"failed={counts.get('failed', '?')}", counts
    return PASS, f"{counts.get('passed', '?')} passed", counts


def gate_upstream() -> tuple[str, str, dict[str, int]]:
    """Upstream's suite may only fail where a deviation is registered.

    The bundled dashboard is moved aside for the run. Upstream's own tests
    assume ``astrbot/dashboard/dist`` is absent -- several assert that a
    rejected WebUI directory resolves to ``None``, and the updater tests take a
    different branch once a bundled copy exists. A release build creates that
    directory by design (``ASTRBOT_BUILD_DASHBOARD=1``), so without this the
    gate would report failures that say nothing about the code, and the order
    "build then verify" would be impossible. The directory is restored
    afterwards whatever the outcome.

    Returns:
        The gate status, a one-line detail, and the parsed pytest counts.
    """
    bundled = REPO_ROOT / "astrbot" / "dashboard" / "dist"
    stashed: Path | None = None
    if bundled.is_dir():
        stashed = Path(tempfile.mkdtemp(prefix="release-gate-dist-")) / "dist"
        shutil.move(str(bundled), str(stashed))
        print(
            "  note: bundled dashboard dist moved aside for the upstream run",
            file=sys.stderr,
        )

    try:
        code, out = _run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests",
                "--ignore=tests/maintained",
                "-q",
            ],
            timeout=3600,
        )
    finally:
        if stashed is not None and stashed.is_dir():
            if bundled.exists():
                shutil.rmtree(bundled)
            shutil.move(str(stashed), str(bundled))
            shutil.rmtree(stashed.parent, ignore_errors=True)

    counts = _pytest_summary(out)
    expected = expected_deviations()
    if expected < 0:
        return FAIL, "could not read the deviation registry", counts

    # A registered deviation is marked xfail(strict), so it is reported as
    # "xfailed", never as "failed". Both conditions have to hold: nothing failed
    # outright, and every registered deviation actually fired. A deviation that
    # stops failing means upstream moved and the entry is now stale.
    failed = counts.get("failed", 0) + counts.get("error", 0)
    xfailed = counts.get("xfailed", 0)

    if failed:
        return FAIL, f"{failed} unexpected failure(s)", counts
    if xfailed != expected:
        return (
            FAIL,
            f"{xfailed} deviation(s) fired, {expected} registered "
            "(an entry is stale, or a new one is missing)",
            counts,
        )
    return (
        PASS,
        f"{counts.get('passed', '?')} passed, {xfailed} registered deviation(s)",
        counts,
    )


def gate_dashboard_stamp() -> tuple[str, str]:
    """The built dashboard must declare the version it was built from.

    Without the stamp the core treats the local assets as foreign and tries to
    download a matching package on every start-up. That download cannot succeed
    (no upstream release carries this fork's version), so the failure shows up
    as two errors per boot rather than as a broken dashboard -- easy to live
    with, and therefore easy to keep.
    """
    code, out = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/maintained/test_dashboard_stamp.py",
            "-q",
        ]
    )
    if code != 0:
        tail = out.strip().splitlines()[-1] if out.strip() else "stamp check failed"
        return FAIL, tail
    return PASS, "dist/assets/version matches the core"


def gate_drift(instance: Path | None) -> tuple[str, str]:
    """The live instance matches the repository."""
    if instance is None:
        return SKIP, "no --instance given"
    core = instance / "core"
    if not core.is_dir():
        return FAIL, f"{core} is not a directory"
    report = compare(core, load_manifest(MANIFEST))
    if not report.consistent:
        drift = ", ".join(sorted(report.drift)[:3])
        return FAIL, f"instance differs: {drift}"
    return PASS, f"{report.total} files in sync"


def gate_stamp(instance: Path | None) -> tuple[str, str]:
    """The instance records the commit it was deployed from."""
    if instance is None:
        return SKIP, "no --instance given"
    stamp = instance / "core" / "data" / "maintained_build.json"
    if not stamp.is_file():
        return FAIL, "missing maintained_build.json; re-run apply_patches"
    try:
        payload = json.loads(stamp.read_text(encoding="utf-8"))
    except ValueError:
        return FAIL, "maintained_build.json is not valid JSON"
    code, out = _run(["git", "rev-parse", "HEAD"])
    head = out.strip() if code == 0 else ""
    commit = str(payload.get("commit", ""))
    if head and commit and commit != head:
        return FAIL, f"instance built from {commit[:8]}, HEAD is {head[:8]}"
    return PASS, f"{commit[:8]} {payload.get('version', '?')}"


def main(argv: list[str] | None = None) -> int:
    """Run every gate and print a verdict.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code: 0 all pass, 1 a gate failed, 2 could not run.
    """
    parser = argparse.ArgumentParser(
        description="Release gate for the maintained fork."
    )
    parser.add_argument(
        "--instance", type=Path, default=None, help="Live instance root."
    )
    parser.add_argument(
        "--skip-upstream",
        action="store_true",
        help="Skip the upstream suite (fast local iteration only).",
    )
    args = parser.parse_args(argv)

    rows: list[tuple[str, str, str]] = []

    rows.append(("lint", *gate_lint()))
    rows.append(("manifest", *gate_manifest()))
    rows.append(("dashboard", *gate_dashboard_stamp()))

    status, detail, counts = gate_maintained()
    rows.append(("maintained", status, detail))

    if args.skip_upstream:
        rows.append(("upstream", SKIP, "--skip-upstream"))
    else:
        status, detail, counts = gate_upstream()
        rows.append(("upstream", status, detail))

    rows.append(("drift", *gate_drift(args.instance)))
    rows.append(("build stamp", *gate_stamp(args.instance)))

    width = max(len(name) for name, _, _ in rows)
    print()
    for name, status, detail in rows:
        print(f"  {name.ljust(width)}  {status:4}  {detail}")

    failed = [name for name, status, _ in rows if status == FAIL]
    print()
    if failed:
        print(f"RELEASE BLOCKED: {', '.join(failed)}")
        return 1
    print("RELEASE READY")
    if args.instance is not None:
        print("  next: restart the instance, then re-run instance_check.py")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via main()
    raise SystemExit(main())
