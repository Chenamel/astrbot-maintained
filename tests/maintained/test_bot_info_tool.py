"""Tests for the built-in bot-info tool.

The point of these tests is the security envelope, not the formatting: the tool
must never take arguments and must never expose configuration values.
"""

from __future__ import annotations

import inspect

import pytest

from astrbot.builtin_stars.bot_info.main import BotInfo


class _FakeProvider:
    def get_model(self) -> str:
        return "test-model-v1"


class _FakeContext:
    def get_using_provider(self, umo: str):
        return _FakeProvider()


class _FakeEvent:
    unified_msg_origin = "test:GroupMessage:1"


def _make(config: dict | None = None) -> BotInfo:
    star = BotInfo.__new__(BotInfo)
    star.context = _FakeContext()
    star.config = config or {}
    return star


@pytest.mark.asyncio
async def test_returns_only_whitelisted_facts() -> None:
    text = await _make().get_bot_info(_FakeEvent())
    assert "AstrBot" in text
    assert "test-model-v1" in text
    # The model needs to know what AstrBot is, otherwise it cannot restate it.
    assert "开源" in text
    assert "名字" in text and "会的事" in text
    # Nothing sensitive may appear.
    for forbidden in ("key", "token", "http", "/", "config", "secret"):
        assert forbidden not in text.lower()


@pytest.mark.asyncio
async def test_disabled_switch_does_not_reveal_switch() -> None:
    text = await _make({"enabled": False}).get_bot_info(_FakeEvent())
    assert "开关" not in text and "未启用" not in text
    assert "AstrBot" not in text


@pytest.mark.asyncio
async def test_optional_fields_can_be_turned_off() -> None:
    text = await _make(
        {"include_plugins": False, "include_uptime": False, "include_abilities": False}
    ).get_bot_info(_FakeEvent())
    assert "已装插件" not in text
    assert "运行时长" not in text
    assert "会的事" not in text
    assert "test-model-v1" in text


def test_tool_takes_no_arguments() -> None:
    """The signature must stay (self, event) -- no user-controlled parameters."""
    params = list(inspect.signature(BotInfo.get_bot_info).parameters)
    assert params == ["self", "event"]
