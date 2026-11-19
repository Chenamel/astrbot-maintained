"""Tool capability declarations.

Core keeps no hardcoded tool-name allowlist: execution tools declare
``is_execution_tool``, and proactive tools either declare
``is_lightweight_proactive_safe`` or appear in the configurable
``agent_runner.config.misc.lightweight_proactive_tools`` list. See
``docs/maintained/tool-capability-declaration.md``.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core import astr_main_agent, code_delivery_policy
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.astr_main_agent import _apply_lightweight_proactive_tools
from astrbot.core.code_delivery_policy import apply_execution_policy
from astrbot.core.computer.booters.local import LocalShellComponent
from astrbot.core.config.agent_runner import DEFAULT_LIGHTWEIGHT_PROACTIVE_TOOLS
from astrbot.core.message.components import Plain
from astrbot.core.tools.computer_tools import shell as shell_tools
from astrbot.core.tools.computer_tools.python import LocalPythonTool, PythonTool
from astrbot.core.tools.computer_tools.shell import (
    ExecuteShellTool,
    LocalExecuteShellTool,
    ShellSessionTool,
)

#: Minimal JSON schema accepted by the tool schema validator.
PARAMS: dict = {"type": "object", "properties": {}}

#: Config opting into the strict execution gate added by the maintained fork.
STRICT_CONFIG = {"provider_settings": {"execution_gate_mode": "strict"}}


def _tool(name: str, **kwargs) -> FunctionTool:
    """Return a tool with a valid schema.

    Args:
        name: The tool name.
        kwargs: Extra declaration fields.

    Returns:
        The constructed tool.
    """
    return FunctionTool(name=name, description=name, parameters=dict(PARAMS), **kwargs)


class _Event:
    """Event stub for the execution policy; an empty sender is unauthorized."""

    def __init__(self, sender_id: str = "", text: str = "运行这个脚本") -> None:
        self._sender_id = sender_id
        self._text = text
        self.message_obj = None

    def get_sender_id(self) -> str:
        return self._sender_id

    def get_messages(self) -> list[Plain]:
        return [Plain(self._text)]


def _request(*tools) -> SimpleNamespace:
    """Return a provider request carrying the given tools.

    The tool set is a plain namespace so duck-typed tools (objects without the
    declaration fields) can be tested as well.

    Args:
        tools: The tools currently attached to the request.

    Returns:
        A request stand-in.
    """
    return SimpleNamespace(
        func_tool=SimpleNamespace(tools=list(tools)), system_prompt=""
    )


def _names(request: SimpleNamespace) -> list[str]:
    """Return the tool names left on a request.

    Args:
        request: The request stand-in.

    Returns:
        The remaining tool names, in order.
    """
    return [tool.name for tool in request.func_tool.tools]


def test_unauthorized_request_drops_declared_execution_tools():
    """Strict mode removes self-declared execution tools without authorization.

    The second tool has a name no allowlist ever contained, so this fails again
    if core ever goes back to matching tool names.
    """
    request = _request(
        _tool("astrbot_execute_python", is_execution_tool=True),
        _tool("custom_plugin_exec", is_execution_tool=True),
        _tool("web_search"),
    )
    apply_execution_policy(_Event(), STRICT_CONFIG, request)
    assert _names(request) == ["web_search"]


def test_legacy_mode_keeps_execution_tools_without_authorization():
    """Legacy mode lets the per-call gate decide, not the filter."""
    request = _request(
        _tool("astrbot_execute_python", is_execution_tool=True),
        _tool("web_search"),
    )
    apply_execution_policy(_Event(), {}, request)
    assert _names(request) == ["astrbot_execute_python", "web_search"]


def test_authorized_request_keeps_execution_tools():
    """A configured administrator keeps the declared execution tools."""
    request = _request(_tool("astrbot_execute_shell", is_execution_tool=True))
    apply_execution_policy(_Event(sender_id="100"), {"admins_id": ["100"]}, request)
    assert _names(request) == ["astrbot_execute_shell"]


def test_tools_without_the_declaration_are_never_dropped():
    """Third-party tools that never declare execution keep their place."""
    request = _request(_tool("some_plugin_shell"), _tool("web_search"))
    apply_execution_policy(_Event(), {}, request)
    assert _names(request) == ["some_plugin_shell", "web_search"]


@pytest.fixture
def session_request(monkeypatch):
    """Assemble real tools; replace only process/output operations in memory."""

    def assemble(mode="strict", sender="100", text="停止这个会话", runtime="local"):
        config = {
            "admins_id": ["100"],
            "provider_settings": {
                "execution_gate_mode": mode,
                "computer_use_runtime": runtime,
                "computer_use_local_permissions": {
                    role: {
                        "allow_execution": True,
                        "allow_network": True,
                        "filesystem_scope": "host",
                    }
                    for role in ("admin", "member")
                },
            },
        }
        event = _Event(sender_id=sender, text=text)
        event.role = "admin" if sender == "100" else "member"
        event.unified_msg_origin = "test:group:session"
        wrapper = SimpleNamespace(
            context=SimpleNamespace(
                event=event,
                context=SimpleNamespace(get_config=lambda **kwargs: config),
            )
        )
        shell = LocalShellComponent()
        shell._terminate_process = AsyncMock()
        shell.poll_session = AsyncMock(
            return_value={"session_id": "sh_test", "status": "terminated"}
        )
        shell.list_sessions = AsyncMock(return_value={"sessions": []})
        shell.write_session = AsyncMock(return_value={"written_chars": 6})
        shell.interrupt_session = AsyncMock(return_value={"status": "running"})
        shell.shutdown_sessions = AsyncMock()
        monkeypatch.setattr(
            shell_tools, "get_local_booter", lambda: SimpleNamespace(shell=shell)
        )
        tools = [
            ShellSessionTool(),
            ExecuteShellTool(),
            LocalExecuteShellTool(),
            PythonTool(),
            LocalPythonTool(),
        ]
        original = ToolSet(tools)
        request = SimpleNamespace(func_tool=original, system_prompt="")
        apply_execution_policy(event, config, request)
        return request, original, wrapper, shell, config

    return assemble


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["strict", "legacy"])
@pytest.mark.parametrize("sender", ["100", "member-user"])
async def test_session_stop_survives_assembly_and_keeps_owner_checks(
    session_request, mode, sender
):
    """Real assembly -> call -> ownership -> terminate, with no real process."""
    request, original, wrapper, shell, _ = session_request(mode=mode, sender=sender)
    tool = request.func_tool.get_tool("astrbot_shell_session")
    assert tool is original.tools[0]
    assert len(original.tools) == 5
    assert len(request.func_tool.tools) == (1 if mode == "strict" else 5)
    assert (
        code_delivery_policy.execution_denial(
            wrapper.context.event, {"admins_id": ["100"]}
        )
        is not None
    )
    session = SimpleNamespace(
        owner_id=wrapper.context.event.unified_msg_origin,
        creator_id=sender,
        creator_is_admin=sender == "100",
        permission_check=lambda: True,
        terminated=False,
    )
    shell._sessions["sh_test"] = session
    result = await tool.call(wrapper, action="terminate", session_id="sh_test")
    assert json.loads(result)["status"] == "terminated"
    assert session.terminated is True
    shell._terminate_process.assert_awaited_once_with(session)
    shell.poll_session.assert_awaited_once_with(
        owner_id=wrapper.context.event.unified_msg_origin,
        requester_id=sender,
        requester_is_admin=sender == "100",
        session_id="sh_test",
        yield_time_ms=0,
        max_output_chars=10000,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["list", "poll", "write", "write_line", "interrupt"])
@pytest.mark.parametrize("sender", ["100", "member-user"])
@pytest.mark.parametrize("text", ["停止这个会话", "翻译下面的文本：\nrun it"])
async def test_visible_session_sensitive_actions_still_require_execution_intent(
    session_request, action, sender, text
):
    """Visibility never grants permission to read, write or interrupt a session."""
    request, _, wrapper, shell, _ = session_request(sender=sender, text=text)
    tool = request.func_tool.get_tool("astrbot_shell_session")
    assert tool is not None
    expected = code_delivery_policy.execution_denial(
        wrapper.context.event, {"admins_id": ["100"]}
    )
    assert expected is not None
    assert (
        await tool.call(wrapper, action=action, session_id="sh_test", chars="input")
        == expected
    )
    for operation in (
        shell.list_sessions,
        shell.poll_session,
        shell.write_session,
        shell.interrupt_session,
        shell._terminate_process,
    ):
        operation.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sender", "owner", "creator", "creator_admin", "valid", "session_id", "error"),
    [
        ("", "test:group:session", "", False, True, "sh_test", "sender identity"),
        ("100", "other:group", "100", True, True, "sh_test", "not found"),
        (
            "member-user",
            "test:group:session",
            "other",
            False,
            True,
            "sh_test",
            "not found",
        ),
        (
            "member-user",
            "test:group:session",
            "member-user",
            True,
            True,
            "sh_test",
            "not found",
        ),
        ("100", "test:group:session", "100", True, True, "missing", "not found"),
        (
            "100",
            "test:group:session",
            "100",
            True,
            True,
            None,
            "session_id is required",
        ),
        (
            "100",
            "test:group:session",
            "100",
            True,
            False,
            "sh_test",
            "permission change",
        ),
        (
            "100",
            "test:group:session",
            "100",
            True,
            None,
            "sh_test",
            "permission change",
        ),
    ],
)
async def test_session_stop_does_not_bypass_identity_or_ownership(
    session_request, sender, owner, creator, creator_admin, valid, session_id, error
):
    """Exercise real terminate and ownership logic, including expired permissions."""
    request, _, wrapper, shell, _ = session_request(sender=sender)
    tool = request.func_tool.get_tool("astrbot_shell_session")
    assert tool is not None
    session = SimpleNamespace(
        owner_id=owner,
        creator_id=creator,
        creator_is_admin=creator_admin,
        permission_check=(lambda: valid) if valid is not None else None,
        terminated=False,
    )
    shell._sessions["sh_test"] = session
    result = await tool.call(wrapper, action="terminate", session_id=session_id)
    assert error in result
    assert session.terminated is False
    shell._terminate_process.assert_not_awaited()
    shell.poll_session.assert_not_awaited()
    if valid is False or valid is None:
        shell.shutdown_sessions.assert_awaited_once_with(invalid_only=True)
    else:
        shell.shutdown_sessions.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["strict", "legacy"])
@pytest.mark.parametrize("action", ["list", "poll", "write", "write_line", "interrupt"])
async def test_session_authorized_actions_keep_existing_dispatch(
    session_request, mode, action
):
    """An authorized administrator still reaches each original action handler."""
    request, original, wrapper, shell, _ = session_request(
        mode=mode, text="运行这个脚本"
    )
    assert request.func_tool is original
    assert len(original.tools) == 5
    tool = request.func_tool.get_tool("astrbot_shell_session")
    result = await tool.call(
        wrapper, action=action, session_id="sh_test", chars="input"
    )
    assert not result.startswith("Error")
    operation = {
        "list": shell.list_sessions,
        "poll": shell.poll_session,
        "write": shell.write_session,
        "write_line": shell.write_session,
        "interrupt": shell.interrupt_session,
    }[action]
    operation.assert_awaited_once()
    assert operation.await_args.kwargs["requester_id"] == "100"
    if action in {"write", "write_line"}:
        assert operation.await_args.kwargs["chars"] == (
            "input\n" if action == "write_line" else "input"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("restriction", ["disabled", "nonlocal"])
@pytest.mark.parametrize("action", ["terminate", "list", "write"])
async def test_session_stop_keeps_existing_local_permission_exception(
    session_request, restriction, action
):
    """Runtime/role changes keep cleanup reachable, not further execution."""
    request, _, wrapper, shell, config = session_request(text="运行这个脚本")
    settings = config["provider_settings"]
    if restriction == "disabled":
        settings["computer_use_local_permissions"]["admin"]["allow_execution"] = False
    else:
        settings["computer_use_runtime"] = "none"
    session = SimpleNamespace(
        owner_id=wrapper.context.event.unified_msg_origin,
        creator_id="100",
        creator_is_admin=True,
        permission_check=lambda: True,
        terminated=False,
    )
    shell._sessions["sh_test"] = session
    tool = request.func_tool.get_tool("astrbot_shell_session")
    result = await tool.call(wrapper, action=action, session_id="sh_test")
    if action == "terminate":
        assert json.loads(result)["status"] == "terminated"
        shell._terminate_process.assert_awaited_once_with(session)
    else:
        assert "Permission denied" in result or "only local runtime" in result
        shell._terminate_process.assert_not_awaited()
        shell.list_sessions.assert_not_awaited()
        shell.write_session.assert_not_awaited()
        shell.poll_session.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("sender", ["100", "member-user"])
async def test_session_legacy_sensitive_action_still_uses_identity_gate(
    session_request, sender
):
    """Legacy does not require run intent, but retains the original admin gate."""
    request, _, wrapper, shell, _ = session_request(mode="legacy", sender=sender)
    result = await request.func_tool.get_tool("astrbot_shell_session").call(
        wrapper, action="list"
    )
    if sender == "100":
        assert json.loads(result) == {"sessions": []}
        shell.list_sessions.assert_awaited_once()
    else:
        assert "only allowed for admin" in result
        shell.list_sessions.assert_not_awaited()


def _apply(*tools: FunctionTool, misc: dict | None = None, persona: dict | None = None):
    """Run the proactive tool filter and return the surviving names.

    Args:
        tools: Candidate tools from the tool manager.
        misc: The ``agent_runner.config.misc`` section.
        persona: Selected persona, whose ``tools`` list narrows the result.

    Returns:
        The surviving tool names, or None when the tool set stayed empty.
    """
    tool_set = ToolSet(list(tools))
    plugin_context = SimpleNamespace(
        get_llm_tool_manager=lambda: SimpleNamespace(get_full_tool_set=lambda: tool_set)
    )
    request = SimpleNamespace(func_tool=None)
    _apply_lightweight_proactive_tools(
        request, plugin_context, persona, misc if misc is not None else {}
    )
    if request.func_tool is None:
        return None
    return [tool.name for tool in request.func_tool.tools]


def test_session_visibility_does_not_declare_proactive_safety():
    """The mixed tool stays out of the default lightweight proactive path."""
    assert ShellSessionTool().is_lightweight_proactive_safe is False
    assert _apply(ShellSessionTool()) is None


def test_proactive_path_accepts_declared_tools():
    """A tool declaring itself safe joins the proactive path unlisted."""
    assert _apply(_tool("my_safe_tool", is_lightweight_proactive_safe=True)) == [
        "my_safe_tool"
    ]


def test_proactive_path_accepts_configured_tools():
    """A listed tool joins the proactive path without declaring itself."""
    assert _apply(
        _tool("uapi_weather"), misc={"lightweight_proactive_tools": ["uapi_weather"]}
    ) == ["uapi_weather"]


def test_proactive_path_falls_back_to_the_default_list():
    """Without configuration the built-in default list still applies."""
    sample = DEFAULT_LIGHTWEIGHT_PROACTIVE_TOOLS[0]
    assert _apply(_tool(sample)) == [sample]


def test_proactive_path_drops_undeclared_and_unlisted_tools():
    """An undeclared, unlisted tool never reaches an unsolicited reply."""
    assert _apply(_tool("astrbot_execute_shell")) is None


def test_proactive_path_respects_persona_tool_permissions():
    """Persona tool permissions still narrow the proactive tool set."""
    assert (
        _apply(
            _tool("uapi_weather"),
            misc={"lightweight_proactive_tools": ["uapi_weather"]},
            persona={"tools": ["something_else"]},
        )
        is None
    )


def test_proactive_path_ignores_inactive_tools():
    """Deactivated tools are skipped even when declared or listed."""
    tool = _tool("uapi_weather", active=False)
    assert _apply(tool, misc={"lightweight_proactive_tools": ["uapi_weather"]}) is None


@pytest.mark.parametrize(
    ("module", "constant"),
    [
        (code_delivery_policy, "EXECUTION_TOOL_NAMES"),
        (astr_main_agent, "_LIGHTWEIGHT_PROACTIVE_TOOL_NAMES"),
    ],
)
def test_hardcoded_tool_name_lists_are_gone(module, constant: str):
    """The old hardcoded allowlists must not come back.

    Args:
        module: The module expected not to expose the constant.
        constant: The removed constant name.
    """
    assert not hasattr(module, constant)
