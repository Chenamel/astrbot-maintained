"""The provider-call detail endpoint's service layer.

The billing-style call log is backed by ``provider_stats``, which already kept
every row -- the dashboard simply had no way to read them back. These tests pin
the query semantics: newest-first pagination, exact-match filters, a summary
that aggregates over the same filters, and local-timezone serialization.
"""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import FastAPI
from sqlmodel import select

from astrbot.core.db.po import ProviderStat
from astrbot.dashboard.api import stats as stats_api
from astrbot.dashboard.services import stat_service
from astrbot.dashboard.services.stat_service import StatService


def _make_service(db) -> StatService:
    """Build a StatService with a real DB and a mocked core lifecycle."""
    core_lifecycle = MagicMock()
    core_lifecycle.start_time = int(time.time()) - 100
    return StatService(db_helper=db, core_lifecycle=core_lifecycle, config={})


async def _seed(
    db,
    *,
    agent_type="internal",
    model="model-a",
    umo="umo-1",
    status="completed",
    tokens=(10, 5, 20),
    ttft=0.5,
    duration=2.0,
):
    """Insert one provider-stat row and return nothing."""
    start = time.time()
    await db.insert_provider_stat(
        umo=umo,
        provider_id=f"prov/{model}",
        provider_model=model,
        status=status,
        stats={
            "token_usage": {
                "input_other": tokens[0],
                "input_cached": tokens[1],
                "output": tokens[2],
            },
            "start_time": start,
            "end_time": start + duration,
            "time_to_first_token": ttft,
        },
        agent_type=agent_type,
    )


@pytest.mark.asyncio
async def test_lists_calls_newest_first(temp_db):
    for i in range(3):
        await _seed(temp_db, model=f"model-{i}")
        time.sleep(0.01)

    result = await _make_service(temp_db).list_provider_calls()

    assert result["total"] == 3
    assert [item["provider_model"] for item in result["items"]] == [
        "model-2",
        "model-1",
        "model-0",
    ]
    assert result["page"] == 1 and result["page_size"] == 50


@pytest.mark.asyncio
async def test_filters_by_model_and_agent_type(temp_db):
    await _seed(temp_db, model="model-a", agent_type="internal")
    await _seed(temp_db, model="model-b", agent_type="llm_generate")
    await _seed(temp_db, model="model-a", agent_type="llm_generate")

    service = _make_service(temp_db)

    by_model = await service.list_provider_calls(provider_model="model-a")
    assert by_model["total"] == 2
    assert all(i["provider_model"] == "model-a" for i in by_model["items"])

    by_type = await service.list_provider_calls(agent_type="llm_generate")
    assert by_type["total"] == 2

    both = await service.list_provider_calls(
        provider_model="model-a", agent_type="internal"
    )
    assert both["total"] == 1


@pytest.mark.asyncio
async def test_summary_aggregates_over_the_same_filters(temp_db):
    await _seed(temp_db, model="model-a", tokens=(10, 5, 20), status="completed")
    await _seed(temp_db, model="model-a", tokens=(1, 2, 3), status="error")
    await _seed(temp_db, model="model-b", tokens=(100, 0, 100), status="completed")

    result = await _make_service(temp_db).list_provider_calls(provider_model="model-a")

    assert result["summary"]["total_calls"] == 2
    assert result["summary"]["token_input_other"] == 11
    assert result["summary"]["token_input_cached"] == 7
    assert result["summary"]["token_output"] == 23
    assert result["summary"]["total_tokens"] == 41
    assert result["summary"]["success_rate"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_pagination_slices_without_losing_total(temp_db):
    for i in range(5):
        await _seed(temp_db, model=f"model-{i}")
        time.sleep(0.01)

    service = _make_service(temp_db)
    page1 = await service.list_provider_calls(page=1, page_size=2)
    page2 = await service.list_provider_calls(page=2, page_size=2)

    assert page1["total"] == 5 and page2["total"] == 5
    assert len(page1["items"]) == 2 and len(page2["items"]) == 2
    models = [i["provider_model"] for i in page1["items"]] + [
        i["provider_model"] for i in page2["items"]
    ]
    assert len(set(models)) == 4


@pytest.mark.asyncio
async def test_rows_expose_token_split_timing_and_status(temp_db):
    await _seed(
        temp_db,
        tokens=(10, 5, 20),
        ttft=0.5,
        duration=2.0,
        status="completed",
    )

    item = (await _make_service(temp_db).list_provider_calls())["items"][0]

    assert item["token_input_other"] == 10
    assert item["token_input_cached"] == 5
    assert item["token_output"] == 20
    assert item["total_tokens"] == 35
    assert item["duration_ms"] == 2000
    assert item["ttft_ms"] == 500
    assert item["status"] == "completed"
    # created_at is stored as UTC and must come back localised and ISO-shaped.
    assert (
        item["created_at"].endswith(("+08:00", "+00:00")) or "T" in item["created_at"]
    )


@pytest.mark.asyncio
async def test_empty_result_keeps_zeroed_summary(temp_db):
    result = await _make_service(temp_db).list_provider_calls(
        provider_model="no-such-model"
    )

    assert result["total"] == 0
    assert result["items"] == []
    assert result["summary"]["total_tokens"] == 0
    assert result["summary"]["success_rate"] == 0


@pytest.mark.asyncio
async def test_agent_type_filter_also_matches_attributed_rows(temp_db):
    """The coarse source filter keeps matching once rows carry a plugin suffix."""
    await _seed(temp_db, agent_type="llm_generate")
    await _seed(temp_db, agent_type="llm_generate:astrbot_plugin_foo")
    await _seed(temp_db, agent_type="internal")

    result = await _make_service(temp_db).list_provider_calls(agent_type="llm_generate")

    assert result["total"] == 2
    assert all(i["agent_type"].startswith("llm_generate") for i in result["items"])


@pytest.mark.asyncio
async def test_caller_filter_narrows_within_an_agent_type(temp_db):
    await _seed(temp_db, agent_type="llm_generate:astrbot_plugin_foo")
    await _seed(temp_db, agent_type="llm_generate:astrbot_plugin_bar")

    result = await _make_service(temp_db).list_provider_calls(
        caller="astrbot_plugin_foo"
    )

    assert result["total"] == 1
    assert result["items"][0]["caller"] == "astrbot_plugin_foo"


@pytest.mark.asyncio
async def test_unattributed_rows_expose_no_caller(temp_db):
    await _seed(temp_db, agent_type="internal")

    item = (await _make_service(temp_db).list_provider_calls())["items"][0]

    assert item["caller"] is None


@pytest.fixture
def overview_clock(monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            fixed = cls(2026, 1, 15, 12, tzinfo=timezone.utc)
            return fixed.astimezone(tz) if tz is not None else fixed

    monkeypatch.setattr(stat_service, "datetime", FixedDatetime)
    return FixedDatetime.now(timezone.utc)


async def _seed_overview(
    db, now, agent_type, *, status="completed", tokens=(10, 5, 20), days_ago=0
):
    await _seed(
        db, agent_type=agent_type, model=agent_type, status=status, tokens=tokens
    )
    async with db.get_db() as session:
        record = (
            (
                await session.execute(
                    select(ProviderStat).order_by(ProviderStat.id.desc())
                )
            )
            .scalars()
            .first()
        )
        record.created_at = now - timedelta(days=days_ago)
        session.add(record)
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "agent_type",
    [
        "internal",
        "llm_generate",
        "llm_generate:plugin_a",
        "proactive_persona",
        "proactive_persona:plugin_a",
        "future_source",
    ],
)
@pytest.mark.parametrize("days", [1, 3, 7])
async def test_overview_counts_every_persisted_call_source(
    temp_db, overview_clock, agent_type, days
):
    await _seed_overview(temp_db, overview_clock, agent_type)
    service = _make_service(temp_db)
    result = await service.get_provider_token_stats(days)
    detail = await service.list_provider_calls()
    assert (
        result["range_total_calls"]
        == result["today_total_calls"]
        == detail["total"]
        == 1
    )
    assert (
        result["range_total_tokens"]
        == result["today_total_tokens"]
        == detail["summary"]["total_tokens"]
        == 35
    )
    assert result["range_success_rate"] == 1
    assert result["range_by_provider"] == [
        {"provider_id": f"prov/{agent_type}", "tokens": 35}
    ]
    assert result["today_by_model"] == [{"provider_model": agent_type, "tokens": 35}]
    assert result["range_by_umo"][0]["tokens"] == 35
    assert sum(tokens for _, tokens in result["trend"]["total_series"]) == 35
    assert result["trend"]["series"][0]["total_tokens"] == 35


@pytest.mark.asyncio
async def test_overview_mixed_sources_keep_success_and_window_rules(
    temp_db, overview_clock
):
    await _seed_overview(temp_db, overview_clock, "internal")
    await _seed_overview(
        temp_db,
        overview_clock,
        "llm_generate:plugin_a",
        status="error",
        tokens=(0, 0, 0),
    )
    await _seed_overview(
        temp_db, overview_clock, "proactive_persona", status="aborted", tokens=(1, 2, 3)
    )
    await _seed_overview(
        temp_db, overview_clock, "proactive_persona", tokens=(100, 100, 100), days_ago=8
    )
    result = await _make_service(temp_db).get_provider_token_stats(1)
    assert result["range_total_calls"] == result["today_total_calls"] == 3
    assert result["range_total_tokens"] == result["today_total_tokens"] == 41
    # Existing overview semantics treat all non-error statuses as successful.
    assert result["range_success_rate"] == pytest.approx(2 / 3)
    assert result["range_avg_ttft_ms"] == 500
    assert result["range_avg_duration_ms"] == 2000
    assert result["range_avg_tpm"] == pytest.approx(23 / (6 / 60))


@pytest.mark.asyncio
async def test_overview_empty_database_keeps_zero_response(temp_db, overview_clock):
    result = await _make_service(temp_db).get_provider_token_stats(1)
    assert result["range_total_calls"] == result["range_total_tokens"] == 0
    assert result["today_total_calls"] == result["today_total_tokens"] == 0
    assert result["range_success_rate"] == 0
    assert result["trend"]["series"] == []
    assert result["range_by_provider"] == result["today_by_model"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path", ["/api/v1/stats/provider-tokens", "/api/stat/provider-tokens"]
)
async def test_overview_routes_serve_all_sources(temp_db, overview_clock, path):
    await _seed_overview(temp_db, overview_clock, "llm_generate:plugin_a")
    await _seed_overview(temp_db, overview_clock, "proactive_persona")
    app = FastAPI()
    app.include_router(stats_api.router, prefix="/api/v1")
    app.include_router(stats_api.legacy_router)
    app.dependency_overrides[stats_api.get_service] = lambda: _make_service(temp_db)
    # Authentication is outside this aggregation regression; use local overrides.
    app.dependency_overrides[stats_api.require_system_scope] = lambda: None
    app.dependency_overrides[stats_api.require_dashboard_user] = lambda: "test"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(path, params={"days": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["data"]["range_total_calls"] == 2
    assert body["data"]["range_total_tokens"] == 70
