"""Tool capability declarations (P3 / T8-04).

Core keeps no hardcoded tool-name allowlist: execution tools declare
``is_execution_tool``, and proactive tools either declare
``is_lightweight_proactive_safe`` or appear in the configurable
``agent_runner.config.misc.lightweight_proactive_tools`` list. See
``docs/maintained/tool-capability-declaration.md``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from astrbot.core import astr_main_agent, code_delivery_policy
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.astr_main_agent import _apply_lightweight_proactive_tools
from astrbot.core.code_delivery_policy import apply_execution_policy
from astrbot.core.config.agent_runner import DEFAULT_LIGHTWEIGHT_PROACTIVE_TOOLS
from astrbot.core.message.components import Plain

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
    """Legacy mode matches upstream: the per-call gate decides, not the filter."""
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
        module: The module that used to own the allowlist.
        constant: The removed constant name.
    """
    assert not hasattr(module, constant)
