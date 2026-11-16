"""A provider call that fails must still leave a record.

Without this the call log goes silent the moment a provider starts refusing
every request: nothing is written, the table stops growing, and the success
rate keeps reading 100% because failures never reach the denominator.
"""

import asyncio
from types import SimpleNamespace

from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
    _record_internal_agent_stats,
)


class _Provider:
    provider_config = {"id": "prov-1"}

    def get_model(self):
        return "model-1"

    def meta(self):
        return SimpleNamespace(id="prov-1")


class _Stats:
    def to_dict(self):
        return {"start_time": 1.0, "end_time": 2.0}


class _Runner:
    def __init__(self, aborted: bool = False):
        self.provider = _Provider()
        self.stats = _Stats()
        self._aborted = aborted

    def was_aborted(self) -> bool:
        return self._aborted


def _event():
    return SimpleNamespace(unified_msg_origin="umo-1")


def _capture(monkeypatch) -> dict:
    captured: dict = {}

    async def fake_insert(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(
        "astrbot.core.db_helper.insert_provider_stat",
        fake_insert,
        raising=True,
    )
    return captured


def test_failed_run_is_recorded_as_error(monkeypatch):
    captured = _capture(monkeypatch)

    asyncio.run(
        _record_internal_agent_stats(_event(), None, _Runner(), None, failed=True)
    )

    assert captured["status"] == "error"
    assert captured["agent_type"] == "internal"
    assert captured["provider_model"] == "model-1"
    assert captured["umo"] == "umo-1"


def test_error_response_is_still_recorded_as_error(monkeypatch):
    captured = _capture(monkeypatch)

    asyncio.run(
        _record_internal_agent_stats(
            _event(),
            None,
            _Runner(),
            SimpleNamespace(role="err"),
            failed=False,
        )
    )

    assert captured["status"] == "error"


def test_successful_run_stays_completed(monkeypatch):
    captured = _capture(monkeypatch)

    asyncio.run(
        _record_internal_agent_stats(
            _event(),
            None,
            _Runner(),
            SimpleNamespace(role="assistant"),
            failed=False,
        )
    )

    assert captured["status"] == "completed"


def test_aborted_run_outranks_failure(monkeypatch):
    """An interruption is reported as such even if it surfaced as an exception."""

    captured = _capture(monkeypatch)

    asyncio.run(
        _record_internal_agent_stats(
            _event(),
            None,
            _Runner(aborted=True),
            None,
            failed=True,
        )
    )

    assert captured["status"] == "aborted"
