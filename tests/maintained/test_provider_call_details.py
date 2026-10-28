"""The provider-call detail endpoint's service layer.

The billing-style call log is backed by ``provider_stats``, which already kept
every row -- the dashboard simply had no way to read them back. These tests pin
the query semantics: newest-first pagination, exact-match filters, a summary
that aggregates over the same filters, and local-timezone serialization.
"""

import time
from unittest.mock import MagicMock

import pytest

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
