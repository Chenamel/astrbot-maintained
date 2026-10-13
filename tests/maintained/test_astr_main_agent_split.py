"""The T8-12 Step 3 split of ``astr_main_agent`` (A + B contracts).

Step 3 moved nine helpers into ``astr_main_agent_quote`` (#38) and
``astr_main_agent_proactive`` (#39) and re-exported them, because the pipeline
stage and the upstream tests resolve them as ``astr_main_agent`` attributes.

Group A pins that contract (including the AST assertion that the
``MainAgentBuildConfig`` call still lives in ``InternalAgentSubStage.initialize``).
Group B pins the behaviour of the moved helpers that had no direct coverage
anywhere, so the move is backed by tests rather than by inspection.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot.core import astr_main_agent, astr_main_agent_proactive, astr_main_agent_quote
from astrbot.core.agent.message import TextPart
from astrbot.core.message.components import Plain, Reply
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.utils.quoted_message.settings import SETTINGS

REPO_ROOT = Path(__file__).resolve().parents[2]
INTERNAL_PATH = (
    REPO_ROOT
    / "astrbot"
    / "core"
    / "pipeline"
    / "process_stage"
    / "method"
    / "agent_sub_stages"
    / "internal.py"
)

#: Symbols that must stay reachable as ``astr_main_agent`` attributes.
REEXPORTED = (
    "WEB_SEARCH_CITATION_PROMPT",
    "WEB_SEARCH_CITATION_TOOL_NAMES",
    "_append_audio_attachment",
    "_append_quoted_audio_attachment",
    "_append_quoted_image_attachment",
    "_apply_web_search_citation_prompt",
    "_apply_web_search_tools",
    "_get_quoted_message_parser_settings",
    "_proactive_cron_job_tools",
    "_process_quote_message",
    "_provider_supports_modality",
)

QUOTE_ALL = (
    "_append_audio_attachment",
    "_append_quoted_audio_attachment",
    "_append_quoted_image_attachment",
    "_get_quoted_message_parser_settings",
    "_process_quote_message",
    "_provider_supports_modality",
)
PROACTIVE_ALL = (
    "WEB_SEARCH_CITATION_PROMPT",
    "WEB_SEARCH_CITATION_TOOL_NAMES",
    "_apply_web_search_citation_prompt",
    "_apply_web_search_tools",
    "_proactive_cron_job_tools",
)

#: Keyword arguments of the MainAgentBuildConfig call captured before Step 3.
EXPECTED_BUILD_KEYWORDS = {
    "tool_call_timeout",
    "tool_schema_mode",
    "hook_timing_mode",
    "sanitize_context_by_modalities",
    "kb_agentic_mode",
    "file_extract_enabled",
    "file_extract_prov",
    "file_extract_msh_api_key",
    "llm_safety_mode",
    "safety_mode_strategy",
    "computer_use_runtime",
    "sandbox_cfg",
    "add_cron_tools",
    "provider_settings",
    "fallback_provider_ids",
    "request_max_retries",
    "subagent_orchestrator",
    "timezone",
    "max_quoted_fallback_images",
}


def _find_build_config_call(tree: ast.Module) -> tuple[ast.Call, ast.AST, ast.AST]:
    """Return the MainAgentBuildConfig call with its enclosing function and class.

    Args:
        tree: Parsed ``internal.py`` module.

    Returns:
        Tuple of the call node, the enclosing function or method and the
        enclosing class.
    """
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "MainAgentBuildConfig"
        ):
            function = parents.get(node)
            while function is not None and not isinstance(
                function,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                function = parents.get(function)
            owner = function
            while owner is not None and not isinstance(owner, ast.ClassDef):
                owner = parents.get(owner)
            return node, function, owner
    raise AssertionError("MainAgentBuildConfig call not found in internal.py")


class _TaskEvent:
    """Event stub carrying the turn extras read by the quote helpers."""

    def __init__(self, message=None, extras: dict | None = None):
        self.message_obj = SimpleNamespace(message=message or [])
        self._extras = dict(extras or {})

    def get_extra(self, key: str, default=None):
        return self._extras.get(key, default)

    def get_platform_name(self) -> str:
        return "aiocqhttp"


class _StubProvider:
    """Provider stub whose modalities are configurable."""

    def __init__(self, modalities=None):
        self.provider_config = {"modalities": modalities}


def test_build_config_is_still_built_in_initialize():
    """The config is built once in the stage initializer, not in __init__.

    The assertion is symbolic: it walks the AST instead of pinning a line
    number, so editing unrelated parts of ``internal.py`` cannot break it.
    """
    tree = ast.parse(INTERNAL_PATH.read_text(encoding="utf-8"))

    call, function, owner = _find_build_config_call(tree)

    assert isinstance(owner, ast.ClassDef)
    assert owner.name == "InternalAgentSubStage"
    assert isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef))
    assert function.name == "initialize"


def test_build_config_keywords_are_unchanged():
    """Every keyword passed to the config survives the split."""
    tree = ast.parse(INTERNAL_PATH.read_text(encoding="utf-8"))
    call, _, _ = _find_build_config_call(tree)
    keywords = {keyword.arg for keyword in call.keywords if keyword.arg}

    assert keywords == EXPECTED_BUILD_KEYWORDS


def test_new_modules_declare_their_public_surface():
    """Both new modules list exactly the symbols they own."""
    assert sorted(astr_main_agent_quote.__all__) == sorted(QUOTE_ALL)
    assert sorted(astr_main_agent_proactive.__all__) == sorted(PROACTIVE_ALL)
    for name in QUOTE_ALL:
        assert callable(getattr(astr_main_agent_quote, name)), name
    for name in PROACTIVE_ALL:
        assert getattr(astr_main_agent_proactive, name) is not None, name


def test_moved_symbols_stay_reachable_from_astr_main_agent():
    """The re-export keeps the upstream tests and internal.py working."""
    missing = [name for name in REEXPORTED if not hasattr(astr_main_agent, name)]
    assert missing == []


def test_citation_constants_are_reexported():
    """Upstream assertions read both citation constants by attribute."""
    assert (
        astr_main_agent.WEB_SEARCH_CITATION_PROMPT
        is astr_main_agent_proactive.WEB_SEARCH_CITATION_PROMPT
    )
    assert (
        astr_main_agent.WEB_SEARCH_CITATION_TOOL_NAMES
        is astr_main_agent_proactive.WEB_SEARCH_CITATION_TOOL_NAMES
    )


def test_internal_stage_imports_the_quote_module():
    """The pipeline stage resolves the quote helpers from #38."""
    tree = ast.parse(INTERNAL_PATH.read_text(encoding="utf-8"))
    modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert "astrbot.core.astr_main_agent_quote" in modules


@pytest.mark.parametrize(
    ("provider_settings", "expected_is_default"),
    [
        (None, True),
        ({"quoted_message_parser": "not-a-dict"}, True),
        ({"quoted_message_parser": {"max_depth": 1}}, False),
    ],
)
def test_quoted_parser_settings_resolution(
    provider_settings,
    expected_is_default: bool,
):
    """Only a dict override replaces the shared default settings.

    Args:
        provider_settings: Provider settings mapping to inspect.
        expected_is_default: Whether the default settings must be returned.
    """
    result = astr_main_agent_quote._get_quoted_message_parser_settings(
        provider_settings,
    )
    assert (result is SETTINGS) is expected_is_default


def test_quoted_image_attachment_text():
    """Quoted images keep their own marker and path."""
    req = ProviderRequest(prompt="", contexts=[])

    astr_main_agent_quote._append_quoted_image_attachment(req, "/tmp/a.png")

    assert req.extra_user_content_parts == [
        TextPart(text="[Image Attachment in quoted message: path /tmp/a.png]")
    ]


def test_audio_attachment_text():
    """Own audio keeps the plain marker."""
    req = ProviderRequest(prompt="", contexts=[])

    astr_main_agent_quote._append_audio_attachment(req, "/tmp/a.wav")

    assert req.extra_user_content_parts == [
        TextPart(text="[Audio Attachment: path /tmp/a.wav]")
    ]


def test_quoted_audio_attachment_text():
    """Quoted audio is labelled as coming from the quoted message."""
    req = ProviderRequest(prompt="", contexts=[])

    astr_main_agent_quote._append_quoted_audio_attachment(req, "/tmp/a.wav")

    assert req.extra_user_content_parts == [
        TextPart(text="[Audio Attachment in quoted message: path /tmp/a.wav]")
    ]


@pytest.mark.asyncio
async def test_process_quote_message_returns_without_a_reply(monkeypatch):
    """An event with no Reply component leaves the request untouched."""
    req = ProviderRequest(prompt="", contexts=[])
    event = _TaskEvent(message=[Plain(text="hello")])

    await astr_main_agent_quote._process_quote_message(
        event,
        req,
        "",
        SimpleNamespace(),
    )

    assert req.extra_user_content_parts == []


@pytest.mark.asyncio
async def test_process_quote_message_appends_the_quote(monkeypatch):
    """A Reply component is rendered as a quoted-message block."""
    captured: dict = {}

    async def fake_extract(event, quote, settings=None):
        captured["settings"] = settings
        captured["event_type"] = type(event).__name__
        return "quoted body"

    monkeypatch.setattr(
        astr_main_agent_quote,
        "extract_quoted_message_text",
        fake_extract,
    )
    req = ProviderRequest(prompt="", contexts=[])
    quote = Reply(id="1", message_str="raw", sender_nickname="nick")
    event = _TaskEvent(message=[quote])

    await astr_main_agent_quote._process_quote_message(
        event,
        req,
        "",
        SimpleNamespace(),
    )

    assert captured["event_type"] == "_TaskEvent"
    assert len(req.extra_user_content_parts) == 1
    text = req.extra_user_content_parts[0].text
    assert text.startswith("<Quoted Message>")
    assert "(nick): quoted body" in text
    assert text.endswith("</Quoted Message>")
