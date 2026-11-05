"""The fork marker has to survive a merge.

``astrbot/__init__.py`` is a file both sides edit -- upstream on every release,
us to keep a local marker. It is also the first file a merge conflict lands on,
and the tempting resolution ("take theirs, it is just a version string") is
silent: the process still starts, every test still passes, and from then on
there is no way to tell a maintained build from an official one in a bug report.

So the marker is pinned here rather than trusted.
"""

from __future__ import annotations

import re
from pathlib import Path

import astrbot

REPO_ROOT = Path(__file__).resolve().parents[2]

#: ``4.28.2+mtn1`` -- an upstream base version plus a local pre-release suffix.
#: PEP 440 allows ``+<local>``, so tooling that parses the version still works.
FORK_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+\+mtn\d+$")


def test_version_carries_the_fork_marker():
    assert FORK_VERSION_RE.match(astrbot.__version__), (
        f"__version__ is {astrbot.__version__!r}; the maintained build must keep "
        "a '+mtnN' suffix so it is distinguishable from an official release."
    )


def test_base_version_is_a_plain_release_number():
    """``__version_base__`` feeds strict ``Version()`` callers, so it must parse.

    The upstream base is what feature detection compares against; the local
    suffix is ours and would break those comparisons.
    """
    assert re.match(r"^\d+\.\d+\.\d+$", astrbot.__version_base__)
    assert astrbot.__version__.startswith(astrbot.__version_base__)


def test_pyproject_and_package_agree_on_the_version():
    """A version bump that updates one file and not the other is a half release.

    The two must match **exactly**, fork suffix included. ``pyproject.toml`` is
    what a wheel is labelled with, so a base-version-only pin would let a built
    package silently drop the marker and become indistinguishable from an
    official release once installed.
    """
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE)

    assert match, "pyproject.toml has no version line"
    assert match.group(1) == astrbot.__version__, (
        f"pyproject has {match.group(1)!r}, package is {astrbot.__version__!r}"
    )


def test_the_version_readme_matches_the_running_version():
    """``README_MAINTAINED.md`` states the base line; it drifts silently."""
    readme = (REPO_ROOT / "README_MAINTAINED.md").read_text(encoding="utf-8")
    mentioned = re.findall(r"v?(\d+\.\d+\.\d+)", readme)

    assert astrbot.__version_base__ in mentioned, (
        f"README_MAINTAINED.md never mentions {astrbot.__version_base__}; "
        f"it mentions {sorted(set(mentioned))[:6]}"
    )


def test_version_file_matches_the_package():
    """``maintained/VERSION`` is a readable copy, so it may not drift.

    Two version strings in one repository is how a release ends up labelled
    differently in two places. The package is the source; this file follows it.
    """
    version_file = REPO_ROOT / "maintained" / "VERSION"
    assert version_file.is_file(), "maintained/VERSION is missing"
    assert version_file.read_text(encoding="utf-8").strip() == astrbot.__version__, (
        f"maintained/VERSION says {version_file.read_text(encoding='utf-8').strip()!r}, "
        f"package is {astrbot.__version__!r}"
    )
