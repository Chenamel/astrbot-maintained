"""Behaviour of the additive runtime-helper module under degradation."""

import os
import pathlib

import pytest

import astrbot.api.runtime as runtime


def test_available_is_boolean():
    assert isinstance(runtime.available(), bool)


def test_data_path_is_absolute_string():
    value = runtime.get_astrbot_data_path()
    assert isinstance(value, str)
    assert value.strip()
    assert os.path.isabs(value)


def test_data_path_falls_back_to_cwd_data():
    if runtime.available():
        return
    assert pathlib.Path(runtime.get_astrbot_data_path()) == pathlib.Path.cwd() / "data"


@pytest.mark.asyncio
async def test_extract_quoted_images_returns_empty_list_when_absent():
    if runtime.available():
        return
    result = await runtime.extract_quoted_message_images(object(), object())
    assert result == []


@pytest.mark.asyncio
async def test_download_fails_loudly_when_absent():
    if runtime.available():
        return
    with pytest.raises(RuntimeError):
        await runtime.download_image_by_url("https://example.com/a.png")


def test_hook_timing_constants_match_the_contract():
    assert runtime.HOOK_TIMING_ENHANCED == "enhanced"
    assert runtime.HOOK_TIMING_LEGACY == "legacy"
    assert runtime.hook_timing_mode() in (
        runtime.HOOK_TIMING_ENHANCED,
        runtime.HOOK_TIMING_LEGACY,
    )


def test_hook_timing_mode_falls_back_when_core_is_absent(monkeypatch):
    monkeypatch.setattr(runtime, "resolve", lambda *args, **kwargs: None)
    assert runtime.hook_timing_mode() == runtime.HOOK_TIMING_ENHANCED


def test_hook_timing_mode_round_trips_and_rejects_unknown_values():
    core_config = pytest.importorskip("astrbot.core.config.agent_runner")
    original = runtime.hook_timing_mode()
    try:
        core_config.set_hook_timing_mode(runtime.HOOK_TIMING_LEGACY)
        assert runtime.hook_timing_mode() == runtime.HOOK_TIMING_LEGACY
        # An invalid mode must keep the fork default instead of switching semantics.
        core_config.set_hook_timing_mode("not-a-mode")
        assert runtime.hook_timing_mode() == runtime.HOOK_TIMING_ENHANCED
    finally:
        core_config.set_hook_timing_mode(original)
