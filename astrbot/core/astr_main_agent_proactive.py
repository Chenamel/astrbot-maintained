"""Optional tool wiring for the main agent build.

Covers the proactive cron tool, the web search tools and the citation prompt,
plus the citation constants. Extracted from ``astr_main_agent`` by T8-12 and
re-exported from there because the upstream tests resolve them as module
attributes.
"""

from __future__ import annotations

from astrbot.core.agent.tool import ToolSet
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.context import Context
from astrbot.core.tools.cron_tools import FutureTaskTool
from astrbot.core.tools.web_search_tools import (
    AnySearchWebSearchTool,
    BaiduWebSearchTool,
    BochaWebSearchTool,
    BraveWebSearchTool,
    ExaGetContentsTool,
    ExaWebSearchTool,
    FirecrawlExtractWebPageTool,
    FirecrawlWebSearchTool,
    TavilyExtractWebPageTool,
    TavilyWebSearchTool,
    normalize_legacy_web_search_config,
)

WEB_SEARCH_CITATION_TOOL_NAMES = frozenset(
    {
        "web_search_baidu",
        "web_search_tavily",
        "web_search_bocha",
        "web_search_brave",
        "web_search_exa",
        "web_search_anysearch",
    }
)

WEB_SEARCH_CITATION_PROMPT = (
    "Always cite web search results you rely on. "
    "Index is a unique identifier for each search result. "
    "Use the exact citation format <ref>index</ref> (e.g. <ref>abcd.3</ref>) "
    "after the sentence that uses the information. Do not invent citations."
)

__all__ = [
    "WEB_SEARCH_CITATION_PROMPT",
    "WEB_SEARCH_CITATION_TOOL_NAMES",
    "_apply_web_search_citation_prompt",
    "_apply_web_search_tools",
    "_proactive_cron_job_tools",
]


def _proactive_cron_job_tools(req: ProviderRequest, plugin_context: Context) -> None:
    if req.func_tool is None:
        req.func_tool = ToolSet()
    tool_mgr = plugin_context.get_llm_tool_manager()
    req.func_tool.add_tool(tool_mgr.get_builtin_tool(FutureTaskTool))


async def _apply_web_search_tools(
    event: AstrMessageEvent,
    req: ProviderRequest,
    plugin_context: Context,
) -> None:
    cfg = plugin_context.get_config(umo=event.unified_msg_origin)
    normalize_legacy_web_search_config(cfg)
    prov_settings = cfg.get("provider_settings", {})

    if not prov_settings.get("web_search", False):
        return

    if req.func_tool is None:
        req.func_tool = ToolSet()

    tool_mgr = plugin_context.get_llm_tool_manager()
    provider = prov_settings.get("websearch_provider", "tavily")
    if provider == "tavily":
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(TavilyWebSearchTool))
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(TavilyExtractWebPageTool))
    elif provider == "bocha":
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(BochaWebSearchTool))
    elif provider == "brave":
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(BraveWebSearchTool))
    elif provider == "firecrawl":
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(FirecrawlWebSearchTool))
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(FirecrawlExtractWebPageTool))
    elif provider == "baidu_ai_search":
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(BaiduWebSearchTool))
    elif provider == "exa":
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(ExaWebSearchTool))
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(ExaGetContentsTool))
    elif provider == "anysearch":
        req.func_tool.add_tool(tool_mgr.get_builtin_tool(AnySearchWebSearchTool))


def _apply_web_search_citation_prompt(
    event: AstrMessageEvent,
    req: ProviderRequest,
) -> None:
    if event.get_platform_name() != "webchat" or not req.func_tool:
        return

    if not any(req.func_tool.get_tool(name) for name in WEB_SEARCH_CITATION_TOOL_NAMES):
        return

    system_prompt = req.system_prompt or ""
    if WEB_SEARCH_CITATION_PROMPT in system_prompt:
        return

    req.system_prompt = f"{system_prompt}\n{WEB_SEARCH_CITATION_PROMPT}\n"
