"""Behaviour of the additive content-part module under degradation."""

from types import SimpleNamespace

import astrbot.api.content as content


def test_available_is_boolean():
    assert isinstance(content.available(), bool)


def test_helpers_never_match_when_types_absent():
    if content.available():
        return
    assert content.is_text_part(SimpleNamespace(text="x")) is False
    assert content.is_image_part(SimpleNamespace()) is False


def test_helpers_tolerate_foreign_objects():
    for candidate in (None, object(), "text", 0, [], {}):
        assert isinstance(content.is_text_part(candidate), bool)
        assert isinstance(content.is_image_part(candidate), bool)


def test_is_image_part_accepts_openai_dict():
    assert content.is_image_part({"type": "image_url", "image_url": {}})
    assert not content.is_image_part({"type": "text", "text": "hi"})


def test_is_text_part_rejects_plain_text_string():
    assert not content.is_text_part("just a string")


def test_types_are_exposed_as_attributes():
    assert hasattr(content, "TextPart")
    assert hasattr(content, "ImageURLPart")
