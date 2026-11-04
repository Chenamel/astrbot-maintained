"""Stamp the built dashboard with the version it was built from.

The core decides whether the assets on disk are usable by comparing
``dist/assets/version`` against its own version. Upstream writes that file in
its release pipeline (``.github/workflows/release.yml``), so a local
``vite build`` produces a dist without it -- and the core then treats perfectly
good assets as incompatible.

What that looks like at start-up: the updater tries to download a matching
package from GitHub using this fork's version, which no upstream release is
tagged with, gets a 404, logs two errors, and falls back to the local copy. The
dashboard works, so it is easy to miss; the cost is two alarming log lines on
every boot and a dependency on the network at start-up.

Usage::

    python scripts/stamp_dashboard_version.py            # uses astrbot.__version__
    python scripts/stamp_dashboard_version.py --version v4.28.2+mtn1
    python scripts/stamp_dashboard_version.py --check    # exit 1 if missing or stale
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DIST = REPO_ROOT / "dashboard" / "dist"
VERSION_FILE = DIST / "assets" / "version"


def _core_version() -> str:
    """Return the version of the package in this working tree.

    Returns:
        ``astrbot.__version__``, without importing the whole package if that can
        be avoided.

    Raises:
        RuntimeError: If the version cannot be read.
    """
    init = REPO_ROOT / "astrbot" / "__init__.py"
    try:
        text = init.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"cannot read {init}: {exc}") from exc
    for line in text.splitlines():
        if line.startswith("__version__"):
            _, _, value = line.partition("=")
            return value.strip().strip("\"'")
    raise RuntimeError(f"no __version__ in {init}")


def main(argv: list[str] | None = None) -> int:
    """Write (or verify) the dashboard version stamp.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns:
        0 on success, 1 when ``--check`` finds the stamp missing or stale.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--version", default=None, help="Override the version to write."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the stamp instead of writing it; exit 1 when it is wrong.",
    )
    args = parser.parse_args(argv)

    if not DIST.is_dir():
        print(
            f"error: {DIST} does not exist; build the dashboard first", file=sys.stderr
        )
        return 1

    version = args.version or _core_version()
    # Upstream writes the release tag, which carries a "v". The comparator
    # normalises it away, but matching upstream keeps the two comparable.
    stamped = version if version.startswith("v") else f"v{version}"

    if args.check:
        if not VERSION_FILE.is_file():
            print(f"missing: {VERSION_FILE.relative_to(REPO_ROOT)}", file=sys.stderr)
            return 1
        current = VERSION_FILE.read_text(encoding="utf-8").strip()
        if current != stamped:
            print(f"stale: has {current!r}, expected {stamped!r}", file=sys.stderr)
            return 1
        print(f"ok: {stamped}")
        return 0

    VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    VERSION_FILE.write_bytes((stamped + "\n").encode("utf-8"))
    print(f"stamped {VERSION_FILE.relative_to(REPO_ROOT)} -> {stamped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
