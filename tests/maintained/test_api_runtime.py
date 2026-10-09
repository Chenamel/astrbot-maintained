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
