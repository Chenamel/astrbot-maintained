"""Forward expansion must be readable, bounded, and never fatal.

A merged forward arrives as a component carrying only an id, and the archive
keeps a placeholder, so the content is readable exactly once: while the event is
alive. These tests pin the three properties that matter -- it renders what the
adapter returns, it stays within the character cap, and a broken adapter or an
unfamiliar payload shape costs nothing but an empty string.
"""

from types import SimpleNamespace

import pytest

from astrbot.core.message.components import Forward
from astrbot.core.utils.forward_expand import (
    FORWARD_MAX_CHARS,
    expand_forward_text,
)


class _Event:
    """Minimal event exposing only what expansion reads."""

    def __init__(self, components, call=None) -> None:
        self._components = components
        self.bot = (
            SimpleNamespace(api=SimpleNamespace(call_action=call)) if call else None
        )

    def get_messages(self):
        return self._components


def _payload(*lines: str) -> dict:
    return {
        "data": {
            "messages": [
                {
                    "sender": {"nickname": "甲"},
                    "content": [{"type": "text", "data": {"text": line}}],
                }
                for line in lines
            ]
        }
    }


@pytest.mark.asyncio
async def test_renders_text_nodes_with_sender_names():
    async def call(action, **params):
        assert action == "get_forward_msg"
        assert params["id"] == "fwd-1"
        return _payload("第一条", "第二条")

    text = await expand_forward_text(_Event([Forward(id="fwd-1")], call))

    assert text.splitlines() == ["甲：第一条", "甲：第二条"]


@pytest.mark.asyncio
async def test_no_forward_means_no_adapter_call():
    called = False

    async def call(action, **params):
        nonlocal called
        called = True
        return _payload("x")

    text = await expand_forward_text(_Event([], call))

    assert text == ""
    assert called is False


@pytest.mark.asyncio
async def test_adapter_without_call_action_yields_empty():
    assert await expand_forward_text(_Event([Forward(id="fwd-1")])) == ""


@pytest.mark.asyncio
async def test_failure_is_swallowed():
    async def call(action, **params):
        raise RuntimeError("adapter exploded")

    assert await expand_forward_text(_Event([Forward(id="fwd-1")], call)) == ""


@pytest.mark.asyncio
async def test_unknown_payload_shape_yields_empty():
    async def call(action, **params):
        return {"data": {"unexpected": True}}

    assert await expand_forward_text(_Event([Forward(id="fwd-1")], call)) == ""


@pytest.mark.asyncio
async def test_text_is_capped():
    async def call(action, **params):
        return _payload("长" * 500, "长" * 500, "长" * 500)

    text = await expand_forward_text(_Event([Forward(id="fwd-1")], call), max_chars=120)

    assert len(text) == 120


@pytest.mark.asyncio
async def test_non_text_segments_become_markers():
    async def call(action, **params):
        return {
            "messages": [
                {
                    "sender": {"nickname": "乙"},
                    "content": [
                        {"type": "text", "data": {"text": "看图"}},
                        {"type": "image", "data": {"file": "a.jpg"}},
                    ],
                }
            ]
        }

    text = await expand_forward_text(_Event([Forward(id="fwd-1")], call))

    assert text == "乙：看图[image]"


def test_cap_is_sane():
    """The default cap must stay small enough to be worth having."""
    assert 200 <= FORWARD_MAX_CHARS <= 4000
