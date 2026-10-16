"""Structure and extraction contracts of ``code_delivery_policy`` (T8-12 Step 2).

Step 2 only extracts two private helpers (``_task_text`` and
``_drop_execution_tools``); it must not touch the T8-10 regexes, the
``execution_denial`` body (lines 38-78) or the unconditional prompt injection.

This file pins both sides of that promise:

- the regex literals stay byte-for-byte identical (a literal snapshot, so any
  edit to a pattern turns the suite red -- which is the *expected* signal when
  T8-10 is finally fixed, see ``docs/maintained/code-delivery-policy.md`` §7);
- the two extracted helpers keep the contracts the inline code had, including
  the ones no existing test covered: the ``removed`` return value, the rebuilt
  ``ToolSet`` type, and the fact that an authorized request is never rebuilt.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot.core import code_delivery_policy as policy
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.message.components import Plain

ADMIN_CONFIG = {"admins_id": ["100"]}

#: The inline regexes of ``execution_denial``, quoted verbatim from the source.
DENIAL_REGEX_LITERALS = (
    (
        "negation",
        r"(?:不要|别|无需|不用|禁止|不必|不能).{0,12}(?:运行|执行|编译)|\b(?:do not|don't|never)\s+(?:run|execute|compile)",
    ),
    (
        "explanation",
        r"(?:解释|介绍|说明|如何|怎么|示例中|代码中|函数名|字符串).{0,12}(?:运行|执行)|\b(?:explain|describe|how to|example of)\b",
    ),
    (
        "authorize_cn",
        r"^(?:(?:请|麻烦|帮我|替我|帮忙|现在|直接|实际|在电脑上|在本机|把这段代码|把这个脚本)\s*)*(?:编译并运行|运行|执行)(?:一下|一遍|它|这|该|代码|程序|脚本|命令|python|shell|cpp|c\+\+|\s|$)",
    ),
    (
        # The T8-10 branch: quoting a document used to count as consent.
        "authorize_then",
        r"|(?:然后|并|再|并且)\s*(?:实际|直接|帮我)?\s*(?:运行|执行)(?:一下|它|这|代码|程序|脚本|命令|\s|$)",
    ),
    (
        # T8-10 fix: a reporting marker means the run verb is quoted, not requested.
        "quoting_marker",
        r"(?i)(?:文档|教程|示例|例子|例如|举例|说明书|readme|注释|书中|官方|这段|上[一面]|下[一面]|里写|写着|说的是|意思是|中提到|里提到)[^。！？!?\n]{0,12}(?:写|说|提到|表示|描述|是|：|:)",
    ),
    (
        "authorize_en",
        r"|^(?:please\s+)?(?:run|execute|compile and run)(?!\s*[=(])(?:\s|$)",
    ),
    (
        "authorize_and_then",
        r"|\b(?:and|then)\s+(?:run|execute)(?!\s*[=(])(?:\s|$)",
    ),
)

#: The compiled refusal pattern, captured before any refactor.
EXPECTED_REFUSAL_PATTERN = (
    r"<refuse\s*/>|这部分不方便展开|"
    r"(?=[\s\S]*(?:违法|非法|伤害|恶意|攻击|暴力|色情|隐私|仇恨|危险|安全限制|"
    r"\b(?:illegal|harm|malware|violence|sexual|privacy|hate|unsafe|dangerous)\b))"
    r"(?=[\s\S]*(?:(?:不能|无法|不会|不方便|不提供|不帮).{0,14}"
    r"(?:协助|提供|编写|生成|展开|帮助)|\b(?:cannot|can't|won't)\s+(?:help|assist|provide)))"
    r"[\s\S]+"
)


def _tool(name: str, **kwargs) -> FunctionTool:
    """Return a tool with a valid schema and optional declaration flags."""
    return FunctionTool(
        name=name,
        description=name,
        parameters={"type": "object", "properties": {}},
        **kwargs,
    )


class _Event:
    """Event stub: an empty sender is unauthorized, the text is an imperative."""

    def __init__(self, sender_id: str = "", text: str = "运行这个脚本") -> None:
        self._sender_id = sender_id
        self._text = text

    def get_sender_id(self) -> str:
        return self._sender_id

    def get_messages(self) -> list[Plain]:
        return [Plain(self._text)]


class _TaskEvent:
    """Event stub carrying the turn extras read by ``_task_text``."""

    def __init__(self, text: str = "写一个 python 脚本", extras: dict | None = None):
        self._text = text
        self._extras = dict(extras or {})

    def get_messages(self) -> list[Plain]:
        return [Plain(self._text)]

    def get_extra(self, key: str, default=None):
        return self._extras.get(key, default)


def _request(*tools, func_tool=None) -> SimpleNamespace:
    """Return a request stand-in, defaulting to a real pydantic ``ToolSet``."""
    return SimpleNamespace(
        func_tool=ToolSet(list(tools)) if func_tool is None else func_tool,
        system_prompt="",
    )


@pytest.mark.parametrize(("name", "literal"), DENIAL_REGEX_LITERALS)
def test_denial_regex_literals_are_untouched(name: str, literal: str):
    """Every inline authorization regex is still present verbatim.

    Args:
        name: Label of the branch under test.
        literal: The exact regex source the module must still contain.
    """
    source = Path(policy.__file__).read_text(encoding="utf-8")
    assert literal in source, f"{name} regex changed: {literal}"


@pytest.mark.parametrize(
    ("extras", "expected_text"),
    [
        ({}, "写一个 python 脚本"),
        ({"_direct_turn_task_text": "写个 python 脚本"}, "写个 python 脚本"),
        (
            {
                "_enhance_followup_direct": True,
                "_enhance_followup_task": "写个 python 脚本",
            },
            "写个 python 脚本\n当前追问：写一个 python 脚本",
        ),
    ],
)
def test_task_text_resolution(extras: dict, expected_text: str):
    """``_task_text`` keeps the extras precedence the inline code had.

    Args:
        extras: Event extras to feed in.
        expected_text: The task text the old inline block would have produced.
    """
    current_text, text, original = policy._task_text(_TaskEvent(extras=extras))
    assert current_text == "写一个 python 脚本"
    assert text == expected_text
    assert original == extras.get("_enhance_followup_task")


def test_drop_execution_tools_returns_the_removed_names_in_order():
    """The helper reports what it removed, in the original tool order."""
    request = _request(
        _tool("astrbot_execute_python", is_execution_tool=True),
        _tool("custom_plugin_exec", is_execution_tool=True),
        _tool("web_search"),
    )

    removed = policy._drop_execution_tools(request)

    assert removed == ["astrbot_execute_python", "custom_plugin_exec"]
    assert [tool.name for tool in request.func_tool.tools] == ["web_search"]


def test_drop_execution_tools_rebuilds_a_real_tool_set():
    """The request keeps a fresh ``ToolSet``, not a mutated plain list.

    The production caller passes a real pydantic ``ToolSet``, so the rebuild --
    not an in-place edit -- is part of the contract.
    """
    original = ToolSet([_tool("astrbot_execute_python", is_execution_tool=True)])
    request = _request(func_tool=original)

    policy._drop_execution_tools(request)

    assert isinstance(request.func_tool, ToolSet)
    assert request.func_tool is not original


def test_drop_execution_tools_keeps_an_empty_tool_set():
    """Dropping every tool leaves an empty ``ToolSet`` rather than ``None``."""
    request = _request(
        _tool("astrbot_execute_python", is_execution_tool=True),
        _tool("astrbot_execute_shell", is_execution_tool=True),
    )

    assert policy._drop_execution_tools(request) == [
        "astrbot_execute_python",
        "astrbot_execute_shell",
    ]
    assert isinstance(request.func_tool, ToolSet)
    assert request.func_tool.tools == []


def test_authorized_request_leaves_the_tool_set_untouched():
    """An authorized request is never rebuilt, so the object identity holds."""
    original = ToolSet([_tool("astrbot_execute_shell", is_execution_tool=True)])
    request = _request(func_tool=original)

    policy.apply_execution_policy(_Event(sender_id="100"), ADMIN_CONFIG, request)

    assert request.func_tool is original


@pytest.mark.parametrize(
    ("sender_id", "tools"),
    [("", 1), ("100", 1), ("", 0)],
)
def test_execution_prompt_is_injected_for_every_outcome(sender_id: str, tools: int):
    """The prompt is appended whether or not execution is authorized.

    Args:
        sender_id: Event sender; empty means unauthorized.
        tools: Number of tools to attach, zero meaning ``func_tool=None``.
    """
    request = (
        _request(_tool("astrbot_execute_python", is_execution_tool=True))
        if tools
        else SimpleNamespace(func_tool=None, system_prompt="")
    )

    policy.apply_execution_policy(_Event(sender_id=sender_id), ADMIN_CONFIG, request)

    assert "Execution authorization is per current message only" in (
        request.system_prompt
    )
    assert "Source-writing tasks must deliver complete source" in request.system_prompt


def test_public_symbols_are_unchanged():
    """The module's public entry points keep their names and parameters."""
    expected = {
        "current_message_text": ["event"],
        "execution_denial": ["event", "config"],
        "code_task_spec": ["event"],
        "has_code_delivery": ["text", "language"],
        "apply_execution_policy": ["event", "config", "request"],
    }
    for name, parameters in expected.items():
        function = getattr(policy, name, None)
        assert callable(function), name
        assert list(inspect.signature(function).parameters) == parameters, name


def test_safety_refusal_pattern_is_untouched():
    """The refusal pattern stays module-level, case-insensitive and identical."""
    assert policy.SAFETY_REFUSAL_PATTERN.pattern == EXPECTED_REFUSAL_PATTERN
    assert policy.SAFETY_REFUSAL_PATTERN.flags & re.I
