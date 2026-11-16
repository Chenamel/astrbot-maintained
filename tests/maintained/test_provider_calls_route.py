"""The per-call log needs its route to exist, not just its service.

The service method kept passing while the route was dropped by a merge, which
is exactly the gap that let the page return 404 with a green suite. These
checks bind the route to the path the frontend actually calls.
"""

from __future__ import annotations

import pathlib
import re

from astrbot.dashboard.api.stats import router

ROOT = pathlib.Path(__file__).resolve().parents[2]
FRONTEND_CLIENT = ROOT / "dashboard" / "src" / "api" / "v1.ts"


def _paths() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for route in router.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        if path:
            out.setdefault(path, set()).update(methods)
    return out


def test_provider_calls_route_is_registered():
    """The detail endpoint must exist on the system-stats router."""
    paths = _paths()
    assert "/stats/provider-calls" in paths
    assert "GET" in paths["/stats/provider-calls"]


def test_frontend_calls_a_route_that_exists():
    """Whatever path the WebUI asks for must be served by this router."""
    source = FRONTEND_CLIENT.read_text(encoding="utf-8")
    called = set(re.findall(r"get\('(/stats/[^']+)'", source))
    called.update(re.findall(r'get\("(/stats/[^"]+)"', source))
    assert called, "no /stats call found in the frontend client"
    missing = sorted(path for path in called if path not in _paths())
    assert not missing, f"frontend calls routes the backend does not serve: {missing}"
