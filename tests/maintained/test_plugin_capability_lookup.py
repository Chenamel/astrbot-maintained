"""Plugin capability discovery in core (P2 / T8-03).

Core must not know any plugin directory name: the proactive helpers find the
plugin by the capability method it exposes and fail closed when nobody
provides it. See ``docs/maintained/plugin-capability-lookup.md``.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.astr_main_agent import _is_lightweight_proactive_request

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Plugin directory names look like ``astrbot_plugin_<name>``. The lookbehind
#: skips path helpers such as ``get_astrbot_plugin_path``.
PLUGIN_DIR_NAME = re.compile(r"(?<![\w])astrbot_plugin_[\w]+")


class FakeEvent:
    """Event stub exposing only the extras the proactive helpers read.

    Args:
        extras: Values returned by ``get_extra``.
    """

    def __init__(self, **extras) -> None:
        self._extras = extras
        self.is_at_or_wake_command = False

    def get_extra(self, key, default=None):
        return self._extras.get(key, default)


class Validating:
    """Capability owner returning a configurable verdict."""

    verdict: object = True
    seen: list = []

    @classmethod
    def is_trusted_lightweight_proactive(cls, event):
        cls.seen.append(event)
        return cls.verdict


class Exploding:
    """Capability owner whose validation raises."""

    @classmethod
    def is_trusted_lightweight_proactive(cls, event):
        raise RuntimeError("validator blew up")


class Finishing:
    """Capability owner recording the completion call."""

    seen: list = []
    raises: bool = False

    @classmethod
    def finish_proactive_request(cls, event):
        cls.seen.append(event)
        if cls.raises:
            raise RuntimeError("finish blew up")


def _trusted_event() -> FakeEvent:
    """Return an event carrying the proactive trigger extras.

    Returns:
        The trusted lightweight proactive event stub.
    """
    return FakeEvent(
        _enhance_proactive_lightweight=True,
        _enhance_active_reply_triggered=True,
        _enhance_followup_direct=False,
    )


def _metadata(star_cls, activated: bool = True) -> SimpleNamespace:
    """Return a stand-in plugin registration entry.

    Args:
        star_cls: The plugin class object, or None.
        activated: Whether the plugin is active.

    Returns:
        A minimal metadata stand-in.
    """
    return SimpleNamespace(activated=activated, star_cls=star_cls)


def _runner_with(event: FakeEvent) -> ToolLoopAgentRunner:
    """Return a runner whose proactive state is untouched.

    Args:
        event: The event the runner carries.

    Returns:
        A runner ready for a first ``_finish_proactive_request`` call.
    """
    runner = ToolLoopAgentRunner()
    runner._proactive_delivery_deferred = False
    runner._proactive_request_finished = False
    runner.run_context = SimpleNamespace(context=SimpleNamespace(event=event))
    return runner


@pytest.fixture(autouse=True)
def _reset_recorded_calls():
    """Clear the class-level recorders between tests."""
    Validating.seen = []
    Finishing.seen = []
    Finishing.raises = False
    Validating.verdict = True


def test_lightweight_proactive_uses_the_capability_owner(monkeypatch):
    """An activated plugin exposing the validator authorizes the trigger."""
    monkeypatch.setattr(
        "astrbot.core.astr_main_agent.star_registry",
        [_metadata(Validating)],
    )
    event = _trusted_event()
    assert _is_lightweight_proactive_request(event) is True
    assert Validating.seen == [event]


@pytest.mark.parametrize(
    "registry",
    [
        [],
        [_metadata(SimpleNamespace())],
        [_metadata(Validating, activated=False)],
        [_metadata(None)],
    ],
)
def test_lightweight_proactive_is_false_without_an_owner(monkeypatch, registry):
    """Nobody exposing the capability means the trigger is not trusted.

    Args:
        monkeypatch: Pytest fixture used to stub the registry.
        registry: The registry contents under test.
    """
    monkeypatch.setattr("astrbot.core.astr_main_agent.star_registry", registry)
    assert _is_lightweight_proactive_request(_trusted_event()) is False


def test_lightweight_proactive_fails_closed_when_validation_raises(monkeypatch):
    """A raising validator is logged and never turns into authorization."""
    monkeypatch.setattr(
        "astrbot.core.astr_main_agent.star_registry",
        [_metadata(Exploding)],
    )
    assert _is_lightweight_proactive_request(_trusted_event()) is False


def test_lightweight_proactive_needs_a_strict_true_verdict(monkeypatch):
    """Only a literal ``True`` from the capability counts as authorization."""
    Validating.verdict = "yes"
    monkeypatch.setattr(
        "astrbot.core.astr_main_agent.star_registry",
        [_metadata(Validating)],
    )
    assert _is_lightweight_proactive_request(_trusted_event()) is False


@pytest.mark.parametrize(
    "extras",
    [
        {},
        {"_enhance_proactive_lightweight": True},
        {
            "_enhance_proactive_lightweight": True,
            "_enhance_active_reply_triggered": True,
            "_enhance_followup_direct": True,
        },
    ],
)
def test_lightweight_proactive_ignores_untrusted_events(monkeypatch, extras):
    """Missing or contradictory extras never authorize the trigger.

    Args:
        monkeypatch: Pytest fixture used to stub the registry.
        extras: The event extras under test.
    """
    monkeypatch.setattr(
        "astrbot.core.astr_main_agent.star_registry",
        [_metadata(Validating)],
    )
    assert _is_lightweight_proactive_request(FakeEvent(**extras)) is False
    assert Validating.seen == []


def test_finish_proactive_request_notifies_the_capability_owner(monkeypatch):
    """The completion cleanup reaches the plugin exposing the capability."""
    monkeypatch.setattr(
        "astrbot.core.star.star.star_registry",
        [_metadata(Finishing)],
    )
    event = FakeEvent(_enhance_active_reply_token="token")
    runner = _runner_with(event)

    runner._finish_proactive_request()
    assert Finishing.seen == [event]


def test_finish_proactive_request_runs_once(monkeypatch):
    """Repeated calls never notify the plugin twice."""
    monkeypatch.setattr(
        "astrbot.core.star.star.star_registry",
        [_metadata(Finishing)],
    )
    runner = _runner_with(FakeEvent(_enhance_active_reply_token="token"))

    runner._finish_proactive_request()
    runner._finish_proactive_request()
    assert len(Finishing.seen) == 1


@pytest.mark.parametrize(
    "registry",
    [[], [_metadata(SimpleNamespace())], [_metadata(Finishing, activated=False)]],
)
def test_finish_proactive_request_is_silent_without_an_owner(monkeypatch, registry):
    """No capability owner means no cleanup and no error.

    Args:
        monkeypatch: Pytest fixture used to stub the registry.
        registry: The registry contents under test.
    """
    monkeypatch.setattr("astrbot.core.star.star.star_registry", registry)
    runner = _runner_with(FakeEvent(_enhance_active_reply_token="token"))

    runner._finish_proactive_request()
    assert Finishing.seen == []


def test_finish_proactive_request_swallows_owner_errors(monkeypatch):
    """A raising cleanup is logged and never escapes the runner."""
    monkeypatch.setattr(
        "astrbot.core.star.star.star_registry",
        [_metadata(Finishing)],
    )
    Finishing.raises = True
    runner = _runner_with(FakeEvent(_enhance_active_reply_token="token"))

    runner._finish_proactive_request()
    assert len(Finishing.seen) == 1


def test_finish_proactive_request_requires_a_token(monkeypatch):
    """Without a proactive token the capability owner is left alone."""
    monkeypatch.setattr(
        "astrbot.core.star.star.star_registry",
        [_metadata(Finishing)],
    )
    runner = _runner_with(FakeEvent())

    runner._finish_proactive_request()
    assert Finishing.seen == []


def test_core_has_no_plugin_directory_names():
    """Core must not name any plugin directory (P2 guard, no allowlist).

    ``astrbot/api/**`` is out of scope: ``astrbot_plugin_web_request`` there is
    an upstream ``ContextVar`` name, not a plugin directory.
    """
    hits = []
    for path in (REPO_ROOT / "astrbot" / "core").rglob("*.py"):
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            for match in PLUGIN_DIR_NAME.finditer(line):
                hits.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {match.group()}")
    assert hits == []
