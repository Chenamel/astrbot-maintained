"""Version endpoints must report the dist the server is actually serving.

A desktop launcher can keep an official ``data/dist`` to satisfy its own
version check while the core serves the fork's dashboard from a separate
directory chosen with ``--webui-dir`` / ``ASTRBOT_WEBUI_DIR``. Reading the
managed dist's stamp in that setup makes ``/api/updates/check`` claim a WebUI
update that does not exist and ``/api/stats/version`` report the wrong current
version. Both endpoints now take the served directory from
``app.state.dashboard_static_folder`` and read its stamp, falling back to the
original lookup when it is absent or unreadable.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from astrbot.core.config.default import VERSION
from astrbot.dashboard.services import stat_service as stat_module
from astrbot.dashboard.services.stat_service import StatService
from astrbot.dashboard.services.update_service import UpdateService

REPO_ROOT = Path(__file__).resolve().parents[2]


class _StubUpdater:
    """Stand-in so check_update never reaches the network."""

    async def check_update(self, consider_prerelease: bool) -> None:
        return None


def _update_service(reader) -> UpdateService:
    return UpdateService(
        _StubUpdater(),
        None,
        get_dashboard_version_func=reader,
        pip_install_func=None,
        demo_mode=False,
        clear_site_data_headers={},
    )


def test_check_update_uses_the_served_dist_stamp() -> None:
    calls: list[Path | None] = []

    async def reader(dist_dir: Path | None = None) -> str | None:
        calls.append(dist_dir)
        return f"v{VERSION}" if dist_dir is not None else "v4.28.2"

    result = asyncio.run(
        _update_service(reader).check_update(None, "/instances/data/dist_maintained")
    )
    assert calls == [Path("/instances/data/dist_maintained")]
    assert result.data["dashboard_version"] == f"v{VERSION}"
    assert result.data["dashboard_has_new_version"] is False


def test_check_update_without_explicit_dir_keeps_the_original_lookup() -> None:
    calls: list[Path | None] = []

    async def reader(dist_dir: Path | None = None) -> str | None:
        calls.append(dist_dir)
        return "v4.28.2"

    result = asyncio.run(_update_service(reader).check_update(None))
    assert calls == [None]
    assert result.data["dashboard_has_new_version"] is True


def test_check_update_falls_back_when_served_stamp_is_missing() -> None:
    calls: list[Path | None] = []

    async def reader(dist_dir: Path | None = None) -> str | None:
        calls.append(dist_dir)
        return None if dist_dir is not None else f"v{VERSION}"

    result = asyncio.run(_update_service(reader).check_update(None, "/served/dist"))
    assert calls == [Path("/served/dist"), None]
    assert result.data["dashboard_has_new_version"] is False


def test_dashboard_type_check_reports_the_served_stamp() -> None:
    async def reader(dist_dir: Path | None = None) -> str | None:
        return f"v{VERSION}"

    result = asyncio.run(
        _update_service(reader).check_update("dashboard", "/served/dist")
    )
    assert result.data["current_version"] == f"v{VERSION}"
    assert result.data["has_new_version"] is False


def test_stat_service_reads_the_served_dist_stamp(monkeypatch, tmp_path) -> None:
    seen: list[Path | None] = []

    async def fake(dist_dir: Path | None = None) -> str | None:
        seen.append(dist_dir)
        return f"v{VERSION}"

    monkeypatch.setattr(stat_module, "get_dashboard_version", fake)
    service = StatService.__new__(StatService)
    assert asyncio.run(service._effective_dashboard_version(tmp_path)) == f"v{VERSION}"
    assert seen == [tmp_path]


def test_stat_service_falls_back_without_a_readable_stamp(
    monkeypatch, tmp_path
) -> None:
    seen: list[Path | None] = []

    async def fake(dist_dir: Path | None = None) -> str | None:
        seen.append(dist_dir)
        return None if dist_dir is not None else "v4.28.2"

    monkeypatch.setattr(stat_module, "get_dashboard_version", fake)
    service = StatService.__new__(StatService)
    assert asyncio.run(service._effective_dashboard_version(tmp_path)) == "v4.28.2"
    assert seen == [tmp_path, None]


def test_both_routes_pass_the_served_folder() -> None:
    """The app.state value must reach both version endpoints, new and legacy."""
    stats = (REPO_ROOT / "astrbot/dashboard/api/stats.py").read_text(
        encoding="utf-8"
    )
    updates = (REPO_ROOT / "astrbot/dashboard/api/updates.py").read_text(
        encoding="utf-8"
    )
    assert stats.count("dashboard_static_folder") >= 4
    assert updates.count("dashboard_static_folder") >= 2
