"""Single tool permission entry (P6 / T8-05).

The admin check and the current-message execution check now share one
implementation, ``check_tool_permission``, while every caller still picks
exactly one level so its strength is unchanged. The upstream modules that never
became fork patches keep calling the frozen ``check_admin_permission`` name,
which forwards to the identity level. See
``docs/maintained/tool-permission-entry.md``.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot.core.tools.computer_tools import util

#: Tool modules inside the computer-use package.
_TOOLS_DIR = Path(util.__file__).parent

#: Call sites kept at their upstream spelling, mapped to their expected count.
_IDENTITY_SITES = {
    _TOOLS_DIR / "cua.py": 3,
    _TOOLS_DIR / "fs.py": 2,
    _TOOLS_DIR / "shipyard_neo" / "browser.py": 3,
    _TOOLS_DIR / "shipyard_neo" / "neo_skills.py": 2,
    _TOOLS_DIR.parent / "message_tools.py": 1,
}

#: Call sites gated by the current-message execution authorization.
_EXECUTION_SITES = {_TOOLS_DIR / "python.py": 2, _TOOLS_DIR / "shell.py": 2}


def _event(role: str = "member", sender_id: str = "42") -> SimpleNamespace:
    """Return an event stand-in.

    Args:
        role: Event role determining admin status.
        sender_id: Reported sender identifier.

    Returns:
        The event stand-in.
    """
    return SimpleNamespace(
        role=role,
        unified_msg_origin="umo",
        message_obj=None,
        get_sender_id=lambda: sender_id,
    )


def _context(event: SimpleNamespace, settings: dict | None = None) -> SimpleNamespace:
    """Return a tool context stand-in around an event.

    Args:
        event: The event stand-in.
        settings: Provider settings reported by the configuration.

    Returns:
        The tool context stand-in.
    """
    return SimpleNamespace(
        context=SimpleNamespace(
            event=event,
            context=SimpleNamespace(
                get_config=lambda umo: {"provider_settings": settings or {}}
            ),
        )
    )


def test_identity_level_denies_non_admins_when_required():
    """Non-admin callers are rejected while the default requirement stands."""
    error = util.check_tool_permission(
        _context(_event()), "File upload/download", util.ToolPermissionLevel.IDENTITY
    )
    assert error is not None
    assert "File upload/download" in error
    assert "42" in error


def test_identity_level_admits_admins():
    """An admin caller is admitted by the identity level."""
    assert (
        util.check_tool_permission(
            _context(_event(role="admin")),
            "File upload/download",
            util.ToolPermissionLevel.IDENTITY,
        )
        is None
    )


def test_identity_level_honours_the_disabled_requirement():
    """Turning the admin requirement off admits members again."""
    context = _context(_event(), {"computer_use_require_admin": False})
    assert (
        util.check_tool_permission(
            context, "File upload/download", util.ToolPermissionLevel.IDENTITY
        )
        is None
    )


def test_execution_level_returns_the_policy_error(monkeypatch):
    """The execution level reports whatever the policy returns."""
    monkeypatch.setattr(util, "execution_denial", lambda event, config: "denied")
    assert (
        util.check_tool_permission(
            _context(_event()), "Shell execution", util.ToolPermissionLevel.EXECUTION
        )
        == "denied"
    )


def test_execution_level_admits_an_authorized_request(monkeypatch):
    """An authorized current message passes the execution level."""
    monkeypatch.setattr(util, "execution_denial", lambda event, config: None)
    assert (
        util.check_tool_permission(
            _context(_event(sender_id="100")),
            "Python execution",
            util.ToolPermissionLevel.EXECUTION,
        )
        is None
    )


def test_execution_level_reads_the_request_configuration(monkeypatch):
    """The execution level forwards the event and its own configuration."""
    seen: list = []
    monkeypatch.setattr(
        util,
        "execution_denial",
        lambda event, config: seen.append((event, config)) or None,
    )
    context = _context(_event(), {"admins_id": ["100"]})
    util.check_tool_permission(
        context, "Python execution", util.ToolPermissionLevel.EXECUTION
    )
    assert [config["provider_settings"]["admins_id"] for _, config in seen] == [["100"]]


def test_levels_stay_independent(monkeypatch):
    """No level ever adds the other check to itself."""
    monkeypatch.setattr(util, "execution_denial", lambda event, config: "denied")
    # the identity level alone stays silent about execution authorization
    assert (
        util.check_tool_permission(
            _context(_event(role="admin")),
            "Shell execution",
            util.ToolPermissionLevel.IDENTITY,
        )
        is None
    )
    # the execution level alone stays silent about admin status
    assert (
        util.check_tool_permission(
            _context(_event(role="admin")),
            "Shell execution",
            util.ToolPermissionLevel.EXECUTION,
        )
        == "denied"
    )


def test_admin_permission_forwards_to_the_identity_level(monkeypatch):
    """The frozen upstream name carries no decision logic of its own."""
    calls: list = []
    monkeypatch.setattr(
        util,
        "check_tool_permission",
        lambda context, operation_name, level: (
            calls.append((operation_name, level)) or "forwarded"
        ),
    )
    context = _context(_event())
    assert util.check_admin_permission(context, "Using CUA mouse") == "forwarded"
    assert calls == [("Using CUA mouse", util.ToolPermissionLevel.IDENTITY)]


def test_the_parallel_entry_point_is_gone():
    """The second fork-owned entry point no longer exists."""
    assert not hasattr(util, "check_execution_permission")


@pytest.mark.parametrize(
    ("path", "expected"), sorted(_IDENTITY_SITES.items(), key=lambda item: str(item[0]))
)
def test_identity_call_sites_are_unchanged(path: Path, expected: int):
    """Upstream-spelled modules still call the frozen admin entry."""
    assert path.read_text(encoding="utf-8").count("check_admin_permission(") == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    sorted(_EXECUTION_SITES.items(), key=lambda item: str(item[0])),
)
def test_execution_call_sites_are_unchanged(path: Path, expected: int):
    """Execution tools still gate on the execution level only."""
    source = path.read_text(encoding="utf-8")
    assert source.count("ToolPermissionLevel.EXECUTION") == expected
