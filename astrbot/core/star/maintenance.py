"""Protect locally maintained plugins from destructive upstream replacement."""

import json
from pathlib import Path

from astrbot.core.utils.astrbot_path import get_astrbot_data_path


class LocalMaintenanceProtectionError(Exception):
    """An upstream replacement would discard a registered local maintenance version."""


def assert_plugin_update_allowed(name: str, root_dir_name: str = "") -> None:
    """Check local protection before any installed plugin replacement.

    Args:
        name: Registered or archive metadata plugin name.
        root_dir_name: Actual installed directory name, when available.

    Raises:
        LocalMaintenanceProtectionError: If protected, or the registry is invalid.
    """
    registry = (
        Path(get_astrbot_data_path())
        / "optimization_tracking"
        / "maintenance_registry.json"
    )
    if not registry.exists():
        return
    try:
        entries = json.loads(registry.read_text(encoding="utf-8"))["protected_plugins"]
        if not isinstance(entries, list) or not all(
            isinstance(item, str) for item in entries
        ):
            raise ValueError("Invalid maintenance entries")
    except (OSError, ValueError, KeyError) as exc:
        raise LocalMaintenanceProtectionError(
            "本地维护名单无法读取，已停止覆盖更新，请先检查维护仓库。"
        ) from exc
    if name in entries or root_dir_name in entries:
        raise LocalMaintenanceProtectionError(
            f"{name} 是本地维护版，已跳过上游覆盖；请使用维护仓库的 update_local.py 合并、回放并生成部署包。"
        )
