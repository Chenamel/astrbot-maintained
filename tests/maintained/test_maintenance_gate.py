"""Local maintenance protection gate (P9 / T8-06).

The registry protects locally maintained plugins from being overwritten or
removed. Missing file: warn and allow (the repo is fork-specific, so blocking
everyone else would lock plugin management entirely). Unreadable file: block.
See ``docs/maintained/maintenance-gate.md``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot.core.star import maintenance
from astrbot.core.star.maintenance import (
    LocalMaintenanceProtectionError,
    assert_plugin_update_allowed,
)
from astrbot.core.star.star_manager import PluginManager


class _Reached(Exception):
    """Raised by the stubbed next step to prove the gate was passed."""


class _RecordingLogger:
    """Logger stand-in capturing warnings."""

    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, message: str, *args) -> None:
        self.warnings.append(message % args if args else message)


@pytest.fixture
def registry(tmp_path, monkeypatch) -> Path:
    """Point the maintenance registry at a temporary data directory.

    Args:
        tmp_path: Pytest temporary directory.
        monkeypatch: Pytest fixture used to redirect the data path.

    Returns:
        The registry file path. The file does not exist yet.
    """
    data_dir = tmp_path / "data"
    (data_dir / "optimization_tracking").mkdir(parents=True)
    monkeypatch.setattr(
        maintenance, "get_astrbot_data_path", lambda: str(data_dir), raising=True
    )
    return data_dir / "optimization_tracking" / "maintenance_registry.json"


def _write(registry: Path, payload: object) -> None:
    """Write the registry file.

    Args:
        registry: The registry file path.
        payload: JSON-serializable payload, or raw text when a string.
    """
    registry.write_text(
        payload if isinstance(payload, str) else json.dumps(payload),
        encoding="utf-8",
    )


def test_missing_registry_warns_and_allows(registry: Path, monkeypatch):
    """A missing registry is reported instead of silently skipping protection.

    Args:
        registry: The (non-existent) registry file path.
        monkeypatch: Pytest fixture used to capture the warning.
    """
    recorder = _RecordingLogger()
    monkeypatch.setattr(maintenance, "logger", recorder)

    assert_plugin_update_allowed("any_plugin")

    assert len(recorder.warnings) == 1
    assert "本地维护" in recorder.warnings[0]
    assert str(registry) in recorder.warnings[0]


@pytest.mark.parametrize(
    ("entries", "name", "root_dir_name"),
    [
        (["my_plugin"], "my_plugin", ""),
        (["my_plugin"], "my_plugin", "some_dir"),
        (["plugin_dir"], "registered_name", "plugin_dir"),
    ],
)
def test_protected_plugins_are_blocked(
    registry: Path, entries: list[str], name: str, root_dir_name: str
):
    """A protected plugin name or directory blocks the change.

    Args:
        registry: The registry file path.
        entries: Protected entries to write.
        name: Plugin name passed to the gate.
        root_dir_name: Directory name passed to the gate.
    """
    _write(registry, {"protected_plugins": entries})
    with pytest.raises(LocalMaintenanceProtectionError):
        assert_plugin_update_allowed(name, root_dir_name)


def test_unprotected_plugins_are_allowed(registry: Path):
    """An unprotected plugin passes the gate.

    Args:
        registry: The registry file path.
    """
    _write(registry, {"protected_plugins": ["other_plugin"]})
    assert_plugin_update_allowed("my_plugin", "my_dir")


@pytest.mark.parametrize(
    "payload",
    [
        "{ not json",
        {},
        {"protected_plugins": "not-a-list"},
        {"protected_plugins": ["ok", 5]},
        {"other_key": []},
    ],
)
def test_unreadable_registry_blocks(registry: Path, payload: object):
    """A corrupt registry fails closed instead of allowing the change.

    Args:
        registry: The registry file path.
        payload: The corrupt payload under test.
    """
    _write(registry, payload)
    with pytest.raises(LocalMaintenanceProtectionError):
        assert_plugin_update_allowed("my_plugin")


def _manager(monkeypatch, protected: str, store_path: str) -> PluginManager:
    """Return a plugin manager whose registry protects one plugin.

    Args:
        monkeypatch: Pytest fixture used to install stubs.
        protected: The protected plugin name.
        store_path: Plugin store directory used after the gate.

    Returns:
        A plugin manager stand-in ready for an uninstall call.
    """
    manager = PluginManager.__new__(PluginManager)
    manager._pm_lock = asyncio.Lock()
    manager.failed_plugin_dict = {protected: {"reserved": False}}
    manager.plugin_store_path = store_path
    manager.plugin_store_path = store_path
    manager.context = SimpleNamespace(
        get_registered_star=lambda name: SimpleNamespace(
            name=name, reserved=False, root_dir_name=f"{name}_dir"
        )
    )
    return manager


@pytest.fixture
def protected_registry(registry: Path) -> Path:
    """Write a registry protecting ``my_plugin`` and its directory.

    Args:
        registry: The registry file path.

    Returns:
        The registry file path.
    """
    _write(registry, {"protected_plugins": ["my_plugin"]})
    return registry


@pytest.mark.asyncio
async def test_uninstall_of_protected_plugin_is_blocked(
    protected_registry: Path, monkeypatch
):
    """Uninstalling a locally maintained plugin is refused by default.

    Args:
        protected_registry: Registry protecting the plugin.
        monkeypatch: Pytest fixture used to install stubs.
    """
    manager = _manager(monkeypatch, "my_plugin", str(protected_registry.parent))
    manager._terminate_plugin = _unreachable

    with pytest.raises(LocalMaintenanceProtectionError):
        await manager.uninstall_plugin("my_plugin")


@pytest.mark.asyncio
async def test_force_uninstall_bypasses_the_gate(protected_registry: Path, monkeypatch):
    """``force=True`` skips the gate; the default path always consults it.

    Args:
        protected_registry: Registry protecting the plugin.
        monkeypatch: Pytest fixture used to install the gate spy.
    """
    calls: list[str] = []
    monkeypatch.setattr(
        "astrbot.core.star.star_manager.assert_plugin_update_allowed",
        lambda name, root_dir_name="": calls.append(name),
    )
    manager = _manager(monkeypatch, "my_plugin", str(protected_registry.parent))

    # Downstream steps need a fully wired manager; only the gate matters here.
    with contextlib.suppress(Exception):
        await manager.uninstall_plugin("my_plugin")
    with contextlib.suppress(Exception):
        await manager.uninstall_plugin("my_plugin", force=True)

    assert calls == ["my_plugin"]


@pytest.mark.asyncio
async def test_uninstall_failed_plugin_respects_the_gate(
    protected_registry: Path, monkeypatch
):
    """The failed-plugin uninstall path uses the same gate.

    Args:
        protected_registry: Registry protecting the plugin.
        monkeypatch: Pytest fixture used to install stubs.
    """
    manager = _manager(monkeypatch, "my_plugin", str(protected_registry.parent))
    manager._cleanup_plugin_state = _raise_reached

    with pytest.raises(LocalMaintenanceProtectionError):
        await manager.uninstall_failed_plugin("my_plugin")
    with pytest.raises(_Reached):
        await manager.uninstall_failed_plugin("my_plugin", force=True)


async def _unreachable(plugin):
    """Fail the test if the gate let an uninstall through."""
    raise AssertionError("the gate must stop an uninstall of a protected plugin")


def _raise_reached(*args, **kwargs):
    """Signal that the flow continued past the gate."""
    raise _Reached()
