"""The fork image helper must follow the upstream prepare_model_image contract.

Upstream 4.29.4 dropped the ``quality`` and ``montage_max_size`` keyword
arguments and changed the return value from a path to a result tuple. The
proactive persona path is the only caller of this helper, and a mismatch there
is swallowed by its broad exception handler, so a regression would otherwise
only show up as a WARN in a live instance.
"""

from __future__ import annotations

import types

import pytest

from astrbot.core.pipeline.process_stage.method.agent_sub_stages import image_input
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.utils.media_utils import ImageInputTooLargeError


class _Event:
    """Minimal event double that records the files the helper claims to own."""

    def __init__(self) -> None:
        self.tracked: list[str] = []
        self.unavailable = False
        self.message_obj = types.SimpleNamespace(message_id="test")

    def track_temporary_local_file(self, path: str) -> None:
        self.tracked.append(path)


@pytest.fixture(autouse=True)
def _stub_visual_flags(monkeypatch):
    monkeypatch.setattr(image_input, "visual_requested", lambda event: False)
    monkeypatch.setattr(
        image_input, "visual_unavailable", lambda event: event.unavailable
    )
    monkeypatch.setattr(
        image_input,
        "set_visual_unavailable",
        lambda event, value: setattr(event, "unavailable", value),
    )


def _stub(
    monkeypatch,
    result,
    seen: dict,
):
    async def _fake(ref: str, **kwargs):
        seen["ref"] = ref
        seen["kwargs"] = kwargs
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(image_input, "prepare_model_image", _fake)


@pytest.mark.asyncio
async def test_only_upstream_kwargs_are_forwarded(monkeypatch, tmp_path):
    """No removed keyword may reach prepare_model_image."""
    seen: dict = {}
    _stub(monkeypatch, ("/tmp/prepared.jpg", False, True, "original"), seen)
    req = ProviderRequest(prompt="hi", image_urls=["https://cdn/x.jpg"])
    event = _Event()

    await image_input.prepare_request_images(
        req,
        event,
        enabled=True,
        max_size=640,
        quality=80,
        output_dir=tmp_path,
        prepared={},
        montage_max_size=640,
    )

    assert seen["kwargs"] == {"max_size": 640, "output_dir": tmp_path}
    assert req.image_urls == ["/tmp/prepared.jpg"]
    assert event.tracked == ["/tmp/prepared.jpg"]


@pytest.mark.asyncio
async def test_reused_original_is_not_tracked(monkeypatch, tmp_path):
    """needs_cleanup=False means the caller must not delete a reused original."""
    seen: dict = {}
    _stub(monkeypatch, ("/data/original.png", False, False, "original"), seen)
    req = ProviderRequest(prompt="hi", image_urls=["https://cdn/x.png"])
    event = _Event()

    await image_input.prepare_request_images(
        req,
        event,
        enabled=True,
        max_size=640,
        quality=80,
        output_dir=tmp_path,
        prepared={},
    )

    assert req.image_urls == ["/data/original.png"]
    assert event.tracked == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [None, ImageInputTooLargeError("/data/oversized.png")],
    ids=["recoverable", "oversized"],
)
async def test_failed_preparation_marks_the_request(monkeypatch, tmp_path, result):
    """Both a plain failure and an oversized input keep the unavailable notice."""
    seen: dict = {}
    _stub(monkeypatch, result, seen)
    req = ProviderRequest(prompt="look at this", image_urls=["https://cdn/x.jpg"])
    event = _Event()

    await image_input.prepare_request_images(
        req,
        event,
        enabled=True,
        max_size=640,
        quality=80,
        output_dir=tmp_path,
        prepared={},
    )

    assert req.image_urls == []
    assert req.image_input_unavailable is True
    assert event.unavailable is True
