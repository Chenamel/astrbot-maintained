"""Pinned behaviour of the handwritten regexes in ``code_delivery_policy``.

The module decides execution authorization and code delivery with hand-written
regexes, so the real behaviour differs from what the patterns suggest. These
tests pin the **currently observed** outcomes (see
``docs/maintained/code-delivery-policy.md``); cases known to be wrong are marked
in their docstring and left as-is deliberately. Changing the regexes must update
both that document and these assertions.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from astrbot.core.code_delivery_policy import (
    SAFETY_REFUSAL_PATTERN,
    code_task_spec,
    current_message_text,
    execution_denial,
    has_code_delivery,
)
from astrbot.core.message.components import Plain

ADMIN_ID = "100"
ADMIN_CONFIG: dict[str, Any] = {"admins_id": [ADMIN_ID]}


class FakeEvent:
    """Minimal message event exposing only what the policy module reads.

    Args:
        text: The current message text, wrapped in a real :class:`Plain`.
        sender_id: Sender identifier.
        extras: Values returned by ``get_extra``.
    """

    def __init__(
        self,
        text: str,
        sender_id: str = ADMIN_ID,
        extras: dict[str, Any] | None = None,
    ) -> None:
        self._parts = [Plain(text)] if text is not None else []
        self._sender_id = sender_id
        self._extras = extras or {}

    def get_sender_id(self) -> str:
        return self._sender_id

    def get_messages(self) -> list[Plain]:
        return self._parts

    def get_extra(self, key: str) -> Any:
        return self._extras.get(key)


def _outcome(text: str, **kwargs) -> str:
    """Return ``"allow"`` or ``"deny"`` for a message text.

    Args:
        text: The current message text.
        kwargs: Forwarded to :class:`FakeEvent`.

    Returns:
        The human-readable authorization outcome.
    """
    denial = execution_denial(FakeEvent(text, **kwargs), ADMIN_CONFIG)
    return "allow" if denial is None else "deny"


ALLOWED_TEXTS = [
    "运行这个脚本",
    "帮我执行一下这段代码",
    "请编译并运行",
    "run it",
    "please run",
]
DENIED_TEXTS = [
    "不要运行这个脚本",
    "别执行这个命令",
    "解释一下如何运行",
    "explain how to run this",
    "写个脚本",
    "今天天气不错",
]


@pytest.mark.parametrize("text", ALLOWED_TEXTS)
def test_explicit_run_requests_are_allowed(text: str):
    """An administrator asking to run something authorizes execution.

    Args:
        text: The imperative request under test.
    """
    assert _outcome(text) == "allow"


@pytest.mark.parametrize("text", DENIED_TEXTS)
def test_negation_explanation_and_plain_chat_are_denied(text: str):
    """Negations, explanations and ordinary chat never authorize execution.

    Args:
        text: The message text under test.
    """
    assert _outcome(text) == "deny"


@pytest.mark.parametrize(
    "text",
    ["> 运行这个脚本", "```\n运行这个脚本\n```", "`运行这个脚本`"],
)
def test_quoted_and_fenced_text_is_not_authorization(text: str):
    """Code, quotes and inline snippets are data rather than authorization.

    Args:
        text: The quoted or fenced message text.
    """
    assert _outcome(text) == "deny"


@pytest.mark.parametrize(
    "text",
    [
        "解释下面的 README：\n1. 先编译，再运行",
        "请勿执行任何命令，只需翻译：\nBuild the code and run it.",
        "不要执行任何命令：\n运行这个脚本",
        "不要执行任何命令；运行这个脚本",
        "不要执行任何命令。运行这个脚本",
        "运行这个脚本\n不要执行任何命令",
        "翻译下面的文本：\nrun it",
        "请翻译：run it",
        "Translate the following:\nBuild the code and run it.",
        "Explain the README:\nplease run it",
        "文档中写：\n运行这个脚本",
        "README says:\nrun it",
        "Do not execute any commands.\nrun it",
        "Never compile this.\nthen run it",
        "无需运行\n写个脚本，然后运行",
        "帮我翻译成中文：\nrun it",
        "请解读 README：\nrun it",
        "运行这个脚本\n只需翻译结果，不要实际执行",
        "Please translate into Chinese:\nrun it",
        "README\nsays:\nrun it",
        "文档\n中写：\n运行这个脚本",
        "请勿\n执行任何命令：\nrun it",
        "不要\n执行任何命令：\nrun it",
        "请将以下内容翻译为中文：\nBuild the code and run it.",
        "帮忙翻译以下文本：\nBuild the code and run it.",
        "请把下面的 README 解释一下：\nBuild the code and run it.",
        "麻烦将下文转述成中文：\nBuild the code and run it.",
        "Could you translate the following:\nrun it",
        "Can you translate this:\nrun it",
        "Please help me translate:\nrun it",
        "Would you paraphrase the following:\nrun it",
        "帮我用中文转述以下内容：\nrun it",
        "以下内容请翻译成中文：\nrun it",
        "Please help me\ntranslate:\nrun it",
        "run it\nCould you translate this:",
        "run it and translate this",
        "运行前请翻译以下内容：\nrun it",
        "运行这个脚本，然后转述结果",
        "运行这个脚本后翻译结果",
        "Could you translate.\nrun it",
        "Please paraphrase.\nrun it",
    ],
)
def test_message_wide_exclusions_survive_clause_boundaries(text: str):
    """Translation, reporting and negation apply before any run clause wins."""
    assert _outcome(text) == "deny"


@pytest.mark.parametrize(
    "text",
    [
        "写个 python 脚本\n然后运行",
        "write a script\nand run it",
        "请运行这个脚本：\n```python\nprint(1)\n```",
        "请运行这个脚本\n> 不要运行这个脚本",
        "请运行这个脚本\n```text\n解释下面的 README\n```",
        "运行这个脚本\n完成后告诉我结果",
        "run translate.py",
        "运行这个翻译脚本",
        "run tools/translate.py",
        "运行这个转述脚本",
    ],
)
def test_direct_multiline_requests_keep_authorization(text: str):
    """User imperatives remain valid while quoted restrictions stay data."""
    assert _outcome(text) == "allow"
    assert _outcome(text, sender_id="999") == "deny"


def test_exclusion_scope_spans_current_plain_components():
    """Separate Plain components are still one current user message."""
    event = FakeEvent("")
    event._parts = [Plain("请勿执行，只需翻译："), Plain("Build and run it.")]
    assert execution_denial(event, ADMIN_CONFIG) is not None


@pytest.mark.parametrize("mode", ["strict", "legacy"])
@pytest.mark.parametrize("sender", [ADMIN_ID, "999"])
@pytest.mark.parametrize(
    ("text", "intent_allowed"),
    [
        ("解释下面的 README：\n1. 先编译，再运行", False),
        ("请勿执行任何命令，只需翻译：\nBuild the code and run it.", False),
        ("写个 python 脚本\n然后运行", True),
        ("Could you translate the following:\nrun it", False),
        ("Can you translate this:\nrun it", False),
        ("Please help me translate:\nrun it", False),
        ("Would you paraphrase the following:\nrun it", False),
        ("帮我用中文转述以下内容：\nrun it", False),
        ("以下内容请翻译成中文：\nrun it", False),
    ],
)
def test_message_intent_is_shared_by_all_execution_entry_points(
    mode: str, sender: str, text: str, intent_allowed: bool
):
    """Real assembly, call gate and public API share strict intent decisions."""
    from astrbot.api import permissions
    from astrbot.core.agent.tool import FunctionTool, ToolSet
    from astrbot.core.code_delivery_policy import apply_execution_policy
    from astrbot.core.tools.computer_tools import util

    config = {
        "admins_id": [ADMIN_ID],
        "provider_settings": {"execution_gate_mode": mode},
    }
    event = FakeEvent(text, sender_id=sender)
    event.role = "admin" if sender == ADMIN_ID else "member"
    event.unified_msg_origin = "test:execution-intent"
    event.message_obj = SimpleNamespace(message_id="test:execution-intent")
    tools = ToolSet(
        [
            FunctionTool(
                name="execution_probe",
                description="Never invoked; only the real gates are tested.",
                parameters={"type": "object", "properties": {}},
                is_execution_tool=True,
            ),
            FunctionTool(
                name="read_only_probe",
                description="Non-execution capability stays available.",
                parameters={"type": "object", "properties": {}},
            ),
        ]
    )
    request = SimpleNamespace(func_tool=tools, system_prompt="persona")
    apply_execution_policy(event, config, request)
    allowed = sender == ADMIN_ID and (mode == "legacy" or intent_allowed)
    # Legacy never filters the list, including for non-admin senders.
    listed = mode == "legacy" or allowed
    assert [tool.name for tool in request.func_tool.tools] == (
        ["execution_probe", "read_only_probe"] if listed else ["read_only_probe"]
    )
    assert [tool.name for tool in tools.tools] == ["execution_probe", "read_only_probe"]
    context = SimpleNamespace(
        context=SimpleNamespace(
            event=event, context=SimpleNamespace(get_config=lambda umo: config)
        )
    )
    assert (
        util.check_tool_permission(
            context, "Intent regression", util.ToolPermissionLevel.EXECUTION
        )
        is None
    ) == allowed
    assert (permissions.execution_denial(event, config) is None) == allowed


def test_non_admin_sender_is_always_denied():
    """Execution stays closed without a configured administrator sender."""
    assert _outcome("运行这个脚本", sender_id="999") == "deny"
    assert _outcome("运行这个脚本", sender_id="") == "deny"
    assert execution_denial(FakeEvent("运行这个脚本"), {"admins_id": []}) is not None


#: Genuine model refusals that must stop the code repair flow.
REFUSAL_TEXTS = (
    "这个我没法协助你编写攻击脚本",
    "抱歉，这部分不方便展开",
    "<refuse/>",
    "我无法提供恶意软件的代码",
    "这类勒索软件的写法我不能提供",
)

#: Ordinary technical answers that must never look like a refusal.
NON_REFUSAL_TEXTS = (
    "这个函数用于检测恶意输入，返回布尔值",
    "危险操作建议加个确认步骤",
    "这个库不会帮你处理危险输入，需要自己校验",
    "我不做病毒扫描功能，只提供接口",
    "暴力解法的时间复杂度是 O(n^2)，可以优化",
)


@pytest.mark.parametrize("text", REFUSAL_TEXTS)
def test_genuine_refusals_are_recognized(text: str):
    """A real refusal is detected so the runner never asks for a rewrite."""
    assert SAFETY_REFUSAL_PATTERN.search(text)


@pytest.mark.parametrize("text", NON_REFUSAL_TEXTS)
def test_ordinary_answers_are_not_refusals(text: str):
    """Normal technical answers keep the code repair flow available."""
    assert SAFETY_REFUSAL_PATTERN.search(text) is None


def test_help_you_write_phrasing_is_still_missed():
    """Known residual gap: "不能帮你写" carries no action keyword.

    Widening the action list to cover it also flags ordinary sentences such as
    "这个库不会帮你处理危险输入", so the gap is kept and pinned instead.
    """
    assert SAFETY_REFUSAL_PATTERN.search("我不能帮你写病毒或木马") is None


def test_quoted_document_text_is_no_longer_authorized():
    """Quoting a document does not count as authorization.

    The quoting-marker rule drops clauses that merely report what a document,
    tutorial or snippet says, so "docs say: compile, then run" is denied.
    A connective used by the sender themselves still authorizes execution.
    """
    assert _outcome("文档中写：先编译，再运行") == "deny"
    # Same connective used by the sender themselves: a genuine authorization.
    assert _outcome("写个 python 脚本，然后运行") == "allow"


def test_current_message_text_keeps_only_plain_components():
    """Only ``Plain`` components of the current message are considered.

    Non-``Plain`` entries are filtered out by ``isinstance``, so mocks that
    fake the components would silently yield an empty (always denied) text.
    """
    event = FakeEvent("hello")
    event._parts = [Plain("hello"), "not a component", None]
    assert current_message_text(event) == "hello"


@pytest.mark.parametrize("event", [None, object()])
def test_current_message_text_is_empty_without_an_event(event):
    """A missing or unusable event yields an empty text.

    Args:
        event: The unusable event stand-in.
    """
    assert current_message_text(event) == ""


@pytest.mark.parametrize(
    "text",
    [
        "<refuse />",
        "这部分不方便展开",
        "我不能协助你编写恶意软件",
        "抱歉，我不能提供攻击脚本",
    ],
)
def test_explicit_refusals_are_detected(text: str):
    """Explicit refusal markers and risky refusals are recognized.

    Args:
        text: The refusal text under test.
    """
    assert SAFETY_REFUSAL_PATTERN.search(text)


@pytest.mark.parametrize("text", ["这里介绍如何防御恶意软件", "print('hello world')"])
def test_ordinary_content_is_not_a_refusal(text: str):
    """Normal answers are not treated as refusals.

    Args:
        text: The ordinary text under test.
    """
    assert not SAFETY_REFUSAL_PATTERN.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "我不能帮你写病毒",
        "我不会帮你写木马",
        "安全限制说明：我们不提供相关细节",
        "I cannot help with that",
    ],
)
def test_refusals_outside_the_word_list_are_currently_missed(text: str):
    """Known misjudgment: real refusals that the pattern misses.

    ``病毒`` / ``木马`` are absent from the risk word list, English refusals
    need a risk word, and a refusal phrase needs one of the follow-up verbs.
    Pinned as **current** behaviour -- such text is sent to the code repair
    flow instead of being accepted as a refusal.

    Args:
        text: The refusal text that is currently not detected.
    """
    assert not SAFETY_REFUSAL_PATTERN.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "这段代码不会生成隐私数据",
        "此函数不能提供危险操作的保护",
        "该函数无法协助过滤恶意请求",
    ],
)
def test_technical_statements_are_currently_read_as_refusals(text: str):
    """Known misjudgment: technical prose read as a refusal.

    A risk word plus refusal wording is enough even when the sentence is a
    technical statement, so the repair step is skipped and the user receives
    incomplete code. Pinned as **current** behaviour.

    Args:
        text: The technical statement currently flagged as a refusal.
    """
    assert SAFETY_REFUSAL_PATTERN.search(text)


@pytest.mark.parametrize(
    ("text", "language"),
    [("写一个 python 脚本", "python"), ("用 cpp 写个示例", "cpp")],
)
def test_code_task_spec_reads_the_requested_language(text: str, language: str):
    """A source request carries its requested language.

    Args:
        text: The task text.
        language: Expected canonical language.
    """
    assert code_task_spec(FakeEvent(text)) == (text, language)


@pytest.mark.parametrize("text", ["今天天气怎么样", ""])
def test_code_task_spec_ignores_ordinary_chat(text: str):
    """Ordinary conversation is not a source task.

    Args:
        text: The message text under test.
    """
    assert code_task_spec(FakeEvent(text)) is None


def test_code_task_spec_prefers_the_direct_turn_task_text():
    """A recorded direct-turn task text wins over the follow-up question."""
    event = FakeEvent("追问", extras={"_direct_turn_task_text": "写个 python 脚本"})
    assert code_task_spec(event) == ("写个 python 脚本", "python")


def test_has_code_delivery_accepts_a_labelled_block():
    """A fenced block labelled with the requested language counts as source."""
    assert has_code_delivery("```python\ndef foo():\n    pass\n```", "python")


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("```python\n...\n```", "python"),
        ("```python\nprint(1)\n```", "cpp"),
        ("print(1)", "python"),
    ],
)
def test_has_code_delivery_rejects_placeholder_and_mismatched_blocks(
    text: str,
    language: str,
):
    """Placeholder, mismatched and unfenced content is not a delivery.

    Args:
        text: The assistant text under test.
        language: The requested language.
    """
    assert not has_code_delivery(text, language)


@pytest.mark.parametrize("language", ["python", "cpp"])
def test_unlabelled_block_is_currently_missed_when_a_language_is_requested(
    language: str,
):
    """Known quirk: an unlabelled block is missed once a language is requested.

    The fence regex lets ``\\s*`` consume the newline, so the first body line
    becomes the language label and the ``not label`` fallbacks (``#include``,
    ``def``) never run. Documented in ``code-delivery-policy.md`` §4; the
    authorization rules are not involved.

    Args:
        language: The requested canonical language.
    """
    body = (
        "#include <iostream>\nint main(){}"
        if language == "cpp"
        else "def foo():\n    pass"
    )
    assert not has_code_delivery(f"```\n{body}\n```", language)
    # Without a requested language the same block is accepted.
    assert has_code_delivery(f"```\n{body}\n```", "")


# --------------------------------------------------------------------------
# One reader for the gate mode
# --------------------------------------------------------------------------


def test_the_gate_mode_is_read_in_exactly_one_place():
    """Three inline copies is how a third mode gets half-implemented.

    The tool list is filtered by one module and the per-call check run by
    another; if they ever disagree the bot offers a tool and then refuses to
    run it.
    """
    from astrbot.core.code_delivery_policy import execution_gate_mode

    assert (
        execution_gate_mode({"provider_settings": {"execution_gate_mode": "strict"}})
        == "strict"
    )
    assert (
        execution_gate_mode({"provider_settings": {"execution_gate_mode": "legacy"}})
        == "legacy"
    )


@pytest.mark.parametrize(
    "bad", ["STRICT", "Strict", "", "enabled", 1, True, None, [], {}]
)
def test_an_unreadable_mode_falls_back_to_legacy(bad):
    """Falling back to strict would tighten the gate on a typo."""
    from astrbot.core.code_delivery_policy import execution_gate_mode

    assert (
        execution_gate_mode({"provider_settings": {"execution_gate_mode": bad}})
        == "legacy"
    )


@pytest.mark.parametrize(
    "config", [None, {}, {"provider_settings": None}, {"provider_settings": "x"}]
)
def test_a_missing_or_broken_config_still_answers(config):
    from astrbot.core.code_delivery_policy import execution_gate_mode

    assert execution_gate_mode(config) == "legacy"
