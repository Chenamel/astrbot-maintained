"""Tooling for release checks, drift detection and daily reports.

See ``docs/maintained/tools.md``. These tools only ever touch the files listed
in ``maintained/installed_manifest.json``; they never read or write instance
data, configuration, or plugins.
"""

from __future__ import annotations

__all__: list[str] = []
