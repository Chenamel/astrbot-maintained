"""Tests for the tool-reaction fallback chain."""

from __future__ import annotations

import pytest

from astrbot.builtin_stars.tool_react.main import ToolReact, _parse_ids


class _Tool:
    def __init__(self, name: str) -> None:
        self.name = name


class _Event:
    platform = "aiocqhttp"

    def __init__(self, fail_on: set[str] | None = None) -> None:
        self.reacted: list[str] = []
        self.fail_on = fail_on or set()

    def get_platform_name(self) -> str:
        return self.platform

    async def react(self, emoji: str) -> None:
        if emoji in self.fail_on:
            raise RuntimeError("protocol rejected")
        self.reacted.append(emoji)


class _Result:
    def __init__(self) -> None:
        self.content = ["original"]


def _make(config: dict | None = None) -> ToolReact:
    star = ToolReact.__new__(ToolReact)
    star.config = config or {}
    return star


def test_parse_ids_ignores_junk() -> None:
    assert _parse_ids("182, 187,abc, 19x ,") == ["182", "187"]


@pytest.mark.asyncio
async def test_first_id_wins() -> None:
    event, result = _Event(), _Result()
    await _make({"enabled": True, "play_song_ids": "182,187"}).on_tool_respond(
        event, _Tool("play_song_by_name"), {}, result
    )
    assert event.reacted == ["182"]


@pytest.mark.asyncio
async def test_falls_back_when_first_id_rejected() -> None:
    event, result = _Event(fail_on={"182"}), _Result()
    await _make({"enabled": True, "play_song_ids": "182,187"}).on_tool_respond(
        event, _Tool("play_song_by_name"), {}, result
    )
    assert event.reacted == ["187"]


@pytest.mark.asyncio
async def test_all_ids_failing_leaves_result_alone() -> None:
    event, result = _Event(fail_on={"182", "187"}), _Result()
    await _make({"enabled": True, "play_song_ids": "182,187"}).on_tool_respond(
        event, _Tool("play_song_by_name"), {}, result
    )
    assert event.reacted == []
    assert result.content == ["original"]


@pytest.mark.asyncio
async def test_ignores_unknown_tools_and_other_platforms() -> None:
    event = _Event()
    await _make({"enabled": True, "play_song_ids": "182"}).on_tool_respond(
        event, _Tool("some_other_tool"), {}, _Result()
    )
    assert event.reacted == []

    event2 = _Event()
    event2.platform = "telegram"
    await _make({"enabled": True, "play_song_ids": "182"}).on_tool_respond(
        event2, _Tool("play_song_by_name"), {}, _Result()
    )
    assert event2.reacted == []


@pytest.mark.asyncio
async def test_disabled_by_default() -> None:
    event = _Event()
    await _make().on_tool_respond(event, _Tool("play_song_by_name"), {}, _Result())
    assert event.reacted == []
