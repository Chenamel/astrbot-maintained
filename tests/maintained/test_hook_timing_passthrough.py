"""Runtime modes reaching the cron and background (sub-agent) wake paths.

Both paths build ``MainAgentBuildConfig`` on their own instead of going through
the pipeline stage, so they must read ``agent_runner.config.misc`` themselves.
Otherwise ``hook_timing_mode`` stays at the dataclass default and ``legacy``
never reaches scheduled or background tasks -- the escape hatch would silently
cover chat only.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.runners.base import AgentState
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from astrbot.core.astr_main_agent import MainAgentBuildConfig
from astrbot.core.cron.manager import CronJobManager

SESSION_STR = "aiocqhttp:GroupMessage:123456"

# (misc section, expected hook_timing_mode, expected tool_schema_mode)
MODE_CASES = [
    ({}, "enhanced", "full"),
    ({"hook_timing_mode": "legacy"}, "legacy", "full"),
    ({"tool_schema_mode": "skills_like"}, "enhanced", "skills_like"),
    (
        {"hook_timing_mode": "legacy", "tool_schema_mode": "skills_like"},
        "legacy",
        "skills_like",
    ),
    # Invalid values keep the defaults instead of switching semantics.
    ({"hook_timing_mode": "nonsense"}, "enhanced", "full"),
    ({"tool_schema_mode": "nonsense"}, "enhanced", "full"),
]


def _config(misc: dict) -> dict:
    """Build a minimal per-conversation config carrying the misc section.

    Args:
        misc: The ``agent_runner.config.misc`` section under test; missing keys
            fall back to the same defaults the production code uses.

    Returns:
        A mapping shaped like the one ``Context.get_config`` returns.
    """
    return {
        "provider_settings": {},
        "agent_runner": {"config": {"persona": {}, "misc": misc}},
    }


async def _no_steps(*args, **kwargs):
    """Yield nothing so the wake path returns right after the build.

    Args:
        args: Ignored; ``step_until_done`` receives the max step count.
        kwargs: Ignored.

    Yields:
        Nothing -- the ``return`` below is hit before any ``yield``.
    """
    return
    yield  # pragma: no cover - only makes this an async generator


def _agent_result() -> MagicMock:
    """Build a stand-in for the ``build_main_agent`` result.

    Returns:
        A mock whose runner yields no step and reports no final response, so
        the wake path returns right after the build.
    """
    result = MagicMock()
    runner = result.agent_runner
    runner.step_until_done = _no_steps
    runner.get_final_llm_resp.return_value = None
    runner.state = AgentState.DONE
    return result


@pytest.fixture
def captured_builds(monkeypatch):
    """Capture every ``MainAgentBuildConfig`` the wake paths build.

    Args:
        monkeypatch: Pytest fixture used to stub the core collaborators.

    Returns:
        The list collecting the configs, in build order.
    """
    builds: list[MainAgentBuildConfig] = []

    async def fake_build_main_agent(*, event, plugin_context, config, req):
        builds.append(config)
        return _agent_result()

    monkeypatch.setattr(
        "astrbot.core.astr_main_agent.build_main_agent",
        fake_build_main_agent,
    )
    monkeypatch.setattr(
        "astrbot.core.astr_main_agent._get_session_conv",
        AsyncMock(return_value=MagicMock(history="[]")),
    )
    monkeypatch.setattr(
        "astrbot.core.cron.manager.persist_agent_history",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "astrbot.core.astr_agent_tool_exec.persist_agent_history",
        AsyncMock(),
    )
    return builds


@pytest.mark.asyncio
@pytest.mark.parametrize(("misc", "expected_mode", "expected_schema"), MODE_CASES)
async def test_cron_wake_passes_misc_runtime_modes(
    captured_builds,
    misc,
    expected_mode,
    expected_schema,
):
    """A cron wake-up honours the configured runtime modes.

    Args:
        captured_builds: Fixture collecting the built configs.
        misc: The ``agent_runner.config.misc`` section under test.
        expected_mode: Expected ``hook_timing_mode`` on the build config.
        expected_schema: Expected ``tool_schema_mode`` on the build config.
    """
    manager = CronJobManager.__new__(CronJobManager)
    manager.ctx = MagicMock()
    manager.ctx.get_config.return_value = _config(misc)

    await manager._woke_main_agent(
        message="run the job",
        session_str=SESSION_STR,
        extras={},
    )

    assert len(captured_builds) == 1
    config = captured_builds[0]
    assert isinstance(config, MainAgentBuildConfig)
    assert config.hook_timing_mode == expected_mode
    assert config.tool_schema_mode == expected_schema


@pytest.mark.asyncio
@pytest.mark.parametrize(("misc", "expected_mode", "expected_schema"), MODE_CASES)
async def test_background_wake_passes_misc_runtime_modes(
    captured_builds,
    misc,
    expected_mode,
    expected_schema,
):
    """A background task result wake-up honours the configured runtime modes.

    Args:
        captured_builds: Fixture collecting the built configs.
        misc: The ``agent_runner.config.misc`` section under test.
        expected_mode: Expected ``hook_timing_mode`` on the build config.
        expected_schema: Expected ``tool_schema_mode`` on the build config.
    """
    event = MagicMock()
    event.unified_msg_origin = SESSION_STR
    event.role = "member"
    ctx = MagicMock()
    ctx.get_config.return_value = _config(misc)
    run_context = MagicMock()
    run_context.context.event = event
    run_context.context.context = ctx
    run_context.tool_call_timeout = 120

    await FunctionToolExecutor._wake_main_agent_for_background_result(
        run_context,
        task_id="task-1",
        tool_name="demo_tool",
        result_text="done",
        tool_args={},
        note="Background task finished.",
        summary_name="demo_tool",
    )

    assert len(captured_builds) == 1
    config = captured_builds[0]
    assert isinstance(config, MainAgentBuildConfig)
    assert config.hook_timing_mode == expected_mode
    assert config.tool_schema_mode == expected_schema
