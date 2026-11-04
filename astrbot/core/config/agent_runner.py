from __future__ import annotations

import copy
from typing import Any

#: Accepted values for ``agent_runner.config.misc.hook_timing_mode``.
HOOK_TIMING_MODES = ("enhanced", "legacy")

#: Default mode: match upstream ("reply first, completion hook after"). The
#: fork optimisation (hook before the reply) stays available through the
#: ``hook_timing_mode`` setting, but is opt-in under the dual-mode rule.
HOOK_TIMING_MODE_DEFAULT = "legacy"

#: Mode that fires the completion hook before the reply is emitted.
HOOK_TIMING_MODE_ENHANCED = "enhanced"

#: Mode that restores the upstream timing ("reply first, completion hook after")
#: on every code path that has an upstream counterpart.
HOOK_TIMING_MODE_LEGACY = "legacy"

#: Fallback allowlist for unsolicited proactive replies. Most of these tools
#: ship with plugins, which cannot declare themselves, so the list stays
#: configurable instead of living in core logic. Tools may also declare
#: ``is_lightweight_proactive_safe`` to opt in without being listed here.
DEFAULT_LIGHTWEIGHT_PROACTIVE_TOOLS = (
    "play_song_by_name",
    "query_lyrics_by_name",
    "enhance_use_image",
    "enhance_memory_rag_read",
    "get_group_message_history",
    "image_studio_get_capabilities",
    "image_studio_view_asset",
    "recall_long_term_memory",
    "grok_web_search",
    "enhance_get_ban_list_status",
    "uapi_weather",
    "uapi_ip_query",
    "uapi_mc_server",
    "uapi_mc_player",
    "uapi_mc_bedrock",
    "uapi_whois",
    "uapi_icp",
    "uapi_tracking",
    "uapi_holiday",
    "uapi_github",
    "uapi_github_user",
    "uapi_steam",
    "uapi_bilibili",
    "uapi_answer_book",
    "uapi_hitokoto",
    "uapi_epic_free",
    "uapi_random_string",
    "uapi_hotboard",
    "uapi_ocr",
)

AGENT_RUNNER_TYPES = ("local", "dify", "coze", "dashscope", "deerflow")
THIRD_PARTY_AGENT_RUNNER_TYPES = AGENT_RUNNER_TYPES[1:]

AGENT_RUNNER_CONFIG_DEFAULTS: dict[str, dict[str, Any]] = {
    "local": {
        "model": {
            "provider_id": "",
            "fallback_provider_ids": [],
            "request_max_retries": 5,
        },
        "persona": {
            "persona_id": "default",
            "safety_mode": True,
            "safety_mode_strategy": "system_prompt",
        },
        "compression": {
            "max_turns": -1,
            "trim_turns": 1,
            "overflow_strategy": "llm_compress",
            "instruction": "",
            "keep_recent_ratio": 0.15,
            "provider_id": "",
            "fallback_max_tokens": 128000,
        },
        "misc": {
            "max_steps": 30,
            "tool_schema_mode": "full",
            "tool_call_timeout": 120,
            "sanitize_context_by_modalities": False,
            "hook_timing_mode": HOOK_TIMING_MODE_DEFAULT,
            "lightweight_proactive_tools": list(DEFAULT_LIGHTWEIGHT_PROACTIVE_TOOLS),
        },
    },
    "dify": {
        "dify_api_type": "chat",
        "dify_api_key": "",
        "dify_api_base": "https://api.dify.ai/v1",
        "dify_workflow_output_key": "astrbot_wf_output",
        "dify_query_input_key": "astrbot_text_query",
        "variables": {},
        "timeout": 60,
        "proxy": "",
    },
    "coze": {
        "coze_api_key": "",
        "bot_id": "",
        "coze_api_base": "https://api.coze.cn",
        "auto_save_history": True,
        "timeout": 60,
        "proxy": "",
    },
    "dashscope": {
        "dashscope_app_type": "agent",
        "dashscope_api_key": "",
        "dashscope_app_id": "",
        "rag_options": {
            "pipeline_ids": [],
            "file_ids": [],
            "output_reference": False,
        },
        "variables": {},
        "timeout": 60,
        "proxy": "",
    },
    "deerflow": {
        "deerflow_api_base": "http://127.0.0.1:2026",
        "deerflow_api_key": "",
        "deerflow_auth_header": "",
        "deerflow_assistant_id": "lead_agent",
        "deerflow_model_name": "",
        "deerflow_thinking_enabled": False,
        "deerflow_plan_mode": False,
        "deerflow_subagent_enabled": False,
        "deerflow_max_concurrent_subagents": 3,
        "deerflow_recursion_limit": 1000,
        "timeout": 300,
        "proxy": "",
    },
}


def get_agent_runner_config_default(runner_type: str) -> dict[str, Any]:
    """Return an isolated default configuration for an Agent Runner type.

    Args:
        runner_type: Short runner type name.

    Returns:
        A deep copy of the runner configuration defaults.

    Raises:
        ValueError: If the runner type is unsupported.
    """
    if runner_type not in AGENT_RUNNER_CONFIG_DEFAULTS:
        raise ValueError(f"Unsupported Agent Runner type: {runner_type}")
    return copy.deepcopy(AGENT_RUNNER_CONFIG_DEFAULTS[runner_type])


def resolve_context_compression_config(
    compression_config: dict[str, Any],
) -> dict[str, Any]:
    """Map session compression settings to main agent build arguments.

    Args:
        compression_config: The ``agent_runner.config.compression`` section.
            An empty mapping preserves the ordinary chat parser's defaults.

    Returns:
        Build arguments shared by chat, Cron and background-result wakeups.
        The input mapping is not modified.
    """
    max_turns = compression_config.get("max_turns", -1)
    trim_turns = compression_config.get("trim_turns", 1)
    dequeue_turns = min(
        max(1, trim_turns), max_turns - 1 if max_turns > 0 else trim_turns
    )
    return {
        "context_limit_reached_strategy": compression_config.get(
            "overflow_strategy", "truncate_by_turns"
        ),
        "llm_compress_instruction": compression_config.get("instruction", ""),
        "llm_compress_keep_recent_ratio": compression_config.get(
            "keep_recent_ratio", 0.15
        ),
        "llm_compress_provider_id": compression_config.get("provider_id", ""),
        "max_context_length": max_turns,
        "dequeue_context_length": max(1, dequeue_turns),
        "fallback_max_context_tokens": compression_config.get(
            "fallback_max_tokens", 128000
        ),
    }


def _normalize_value(value: Any, default: Any) -> Any:
    if isinstance(default, dict):
        if not isinstance(value, dict):
            return copy.deepcopy(default)
        if not default:
            return copy.deepcopy(value)
        return {
            key: _normalize_value(value.get(key), child_default)
            for key, child_default in default.items()
        }
    if isinstance(default, list):
        return (
            copy.deepcopy(value) if isinstance(value, list) else copy.deepcopy(default)
        )
    if isinstance(default, bool):
        return value if isinstance(value, bool) else default
    if isinstance(default, int):
        if isinstance(value, bool):
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    if isinstance(default, float):
        if isinstance(value, bool):
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    if isinstance(default, str):
        return value if isinstance(value, str) else default
    return copy.deepcopy(value) if value is not None else copy.deepcopy(default)


def normalize_agent_runner(agent_runner: object) -> dict[str, Any]:
    """Validate and normalize a complete Agent Runner configuration.

    Args:
        agent_runner: Untrusted root Agent Runner configuration.

    Returns:
        A normalized configuration containing only fields for the selected runner.

    Raises:
        ValueError: If the root value or runner type is invalid.
    """
    if not isinstance(agent_runner, dict):
        raise ValueError("agent_runner must be an object")
    runner_type = agent_runner.get("runner_type")
    if runner_type not in AGENT_RUNNER_TYPES:
        raise ValueError(f"Unsupported Agent Runner type: {runner_type}")
    config = agent_runner.get("config", {})
    default = AGENT_RUNNER_CONFIG_DEFAULTS[runner_type]
    normalized = _normalize_value(config, default)
    if runner_type == "local":
        ratio = normalized["compression"]["keep_recent_ratio"]
        normalized["compression"]["keep_recent_ratio"] = min(0.3, max(0.0, ratio))
        if normalized["model"]["request_max_retries"] < 1:
            normalized["model"]["request_max_retries"] = 1
        if normalized["misc"]["max_steps"] < 1:
            normalized["misc"]["max_steps"] = 1
        if normalized["compression"]["trim_turns"] < 1:
            normalized["compression"]["trim_turns"] = 1
    return {"runner_type": runner_type, "config": normalized}


#: Mode recorded by the most recent main agent build (see :func:`set_hook_timing_mode`).
#:
#: This is a **fallback for callers with no event in hand**, not the source of
#: truth: the mode is per configuration, and a process can serve several bots
#: whose profiles disagree. Anything that has an event should pass it, so it
#: reads the snapshot taken when its own turn started.
_CURRENT_HOOK_TIMING_MODE = HOOK_TIMING_MODE_DEFAULT

#: Event extra holding the mode that was in effect when a turn started.
HOOK_TIMING_EXTRA = "_hook_timing_mode"


def normalize_hook_timing_mode(value: Any) -> str:
    """Return a supported hook timing mode, falling back to the default.

    Args:
        value: The raw configured value.

    Returns:
        ``value`` when it is one of :data:`HOOK_TIMING_MODES`, otherwise
        :data:`HOOK_TIMING_MODE_DEFAULT`. Invalid values therefore keep the
        current behaviour instead of silently switching semantics.
    """
    if isinstance(value, str) and value in HOOK_TIMING_MODES:
        return value
    return HOOK_TIMING_MODE_DEFAULT


def hook_timing_mode(event: Any = None) -> str:
    """Return the hook timing mode of the turn being served.

    Args:
        event: The message event, when the caller has one. Its snapshot wins,
            because it describes the configuration that built this turn.

    Returns:
        ``"enhanced"`` or ``"legacy"``. With an event carrying a snapshot, that
        value; otherwise the mode of the most recent main agent build, or the
        default before any build has run.

    Notes:
        Without the event argument this reads process-wide state, which is only
        correct while every bot in the process shares one profile. That is the
        assumption this parameter exists to remove.
    """
    if event is not None:
        snapshot = _extra(event, HOOK_TIMING_EXTRA)
        if isinstance(snapshot, str) and snapshot in HOOK_TIMING_MODES:
            return snapshot
    return normalize_hook_timing_mode(_CURRENT_HOOK_TIMING_MODE)


def set_hook_timing_mode(value: Any, event: Any = None) -> str:
    """Record the hook timing mode of a main agent build and return it.

    Args:
        value: The raw configured value.
        event: The message event this build serves. When given, the mode is
            also written onto the event so later reads do not depend on the
            most recent build winning a race.

    Returns:
        The normalized mode that is now in effect.
    """
    global _CURRENT_HOOK_TIMING_MODE
    normalized = normalize_hook_timing_mode(value)
    _CURRENT_HOOK_TIMING_MODE = normalized
    if event is not None:
        setter = getattr(event, "set_extra", None)
        if callable(setter):
            try:
                setter(HOOK_TIMING_EXTRA, normalized)
            except Exception:  # noqa: BLE001 - event contract is duck-typed
                pass
    return normalized


def _extra(event: Any, key: str) -> Any:
    """Read an event extra without assuming the full event contract."""
    getter = getattr(event, "get_extra", None)
    if not callable(getter):
        return None
    try:
        return getter(key)
    except Exception:  # noqa: BLE001
        return None
