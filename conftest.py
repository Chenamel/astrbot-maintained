"""Pytest configuration for the maintained AstrBot fork.

Upstream tests that this fork fails **on purpose** (P11) are marked as
``xfail(strict=True)`` from here instead of being edited in place: the
zero-conflict rule in the ``project_rules`` document (section 3) forbids
touching upstream files. The deviations themselves are registered in
``maintained/p11_deviations.py``.

Because the marker is strict, an upstream test that starts passing again -- which
means the deviation was reverted or overwritten by an upstream merge -- is
reported as ``XPASS(strict)`` and fails the suite on purpose.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

MAINTAINED_DIR = Path(__file__).resolve().parent / "maintained"
if str(MAINTAINED_DIR) not in sys.path:
    sys.path.insert(0, str(MAINTAINED_DIR))


def pytest_collection_modifyitems(config, items):
    """Mark the known upstream deviations as strict expected failures.

    Args:
        config: The pytest configuration (unused, kept for the hook signature).
        items: The collected test items, mutated in place.
    """
    # Imported here so the module stays importable without the path tweak above
    # having run first; ``tests/maintained/conftest.py`` imports it the same way,
    # so both share one module instance (and one ``APPLIED`` list).
    import p11_deviations

    for item in items:
        entry = p11_deviations.reason_for(item.nodeid)
        if entry is None:
            continue
        item.add_marker(pytest.mark.xfail(reason=entry[1], strict=True))
        p11_deviations.APPLIED.append(item.nodeid)
