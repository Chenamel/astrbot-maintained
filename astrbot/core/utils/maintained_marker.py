"""One line that says which build is running.

Upstream prints ``AstrBot v<version>``. This fork appends a local segment
(``4.28.2+mtn1``), so the version string already differs -- but only for a
reader who knows what ``+mtn1`` means. The banner in ``main.py`` is the first
thing on screen and is easy to check against a screenshot, so the marker is
printed there too, as a phrase rather than a suffix.

Printing it can happen from more than one entry point: ``main.py`` prints the
logo itself, and ``AstrBotCoreLifecycle.initialize`` runs afterwards and prints
its own version line. Both would show the marker, which reads as a bug. The
guard below keeps it to once per process regardless of entry point.
"""

from __future__ import annotations

import os

#: Set once the marker has been printed, so a second entry point stays quiet.
_PRINTED_ENV = "ASTRBOT_MAINTAINED_MARKER_PRINTED"


def maintained_marker(version: str, base_version: str) -> str:
    """Return the line that identifies a maintained build, or ``""``.

    Args:
        version: The running package version, e.g. ``4.28.2+mtn1``.
        base_version: The same version without the local segment, e.g. ``4.28.2``.

    Returns:
        ``"AstrBot Maintained Fork v4.28.2+mtn1"`` when the two differ, which is
        what marks this as a fork rather than an official release. An empty
        string on an official build, so callers can print it unconditionally.
    """
    if version == base_version:
        return ""
    return f"AstrBot Maintained Fork v{version}"


def claim_marker_slot() -> bool:
    """Return whether this caller is the one that should print the marker.

    The first caller in a process wins; later ones get ``False``. Uses the
    environment rather than a module global because ``main.py`` and the core
    are imported through different ``sys.path`` roots when the package is
    installed, which can produce two module instances.

    Returns:
        ``True`` for the first caller in this process, ``False`` afterwards.
    """
    if os.environ.get(_PRINTED_ENV):
        return False
    os.environ[_PRINTED_ENV] = "1"
    return True
