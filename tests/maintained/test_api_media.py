"""Behaviour of the additive media contract under degradation."""

from types import SimpleNamespace

import astrbot.api.media as media


def _request(**kwargs):
    base = {
        "image_urls": [],
        "extra_user_content_parts": [],
        "image_input_unavailable": None,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_caption_marker_is_stable():
    assert media.IMAGE_CAPTION_MARKER == "<image_caption>"


def test_constants_are_non_empty_strings():
    assert isinstance(media.IMAGE_INPUT_UNAVAILABLE_MESSAGE, str)
    assert media.IMAGE_INPUT_UNAVAILABLE_MESSAGE.strip()
    assert isinstance(media.IMAGE_INPUT_UNAVAILABLE_NOTICE, str)
    assert media.IMAGE_INPUT_UNAVAILABLE_NOTICE.strip()


def test_notice_contains_message():
    assert media.IMAGE_INPUT_UNAVAILABLE_MESSAGE in media.IMAGE_INPUT_UNAVAILABLE_NOTICE


def test_mirror_text_when_core_contract_absent():
    if media.available():
        return
    assert media.IMAGE_INPUT_UNAVAILABLE_MESSAGE == "当前看不到图片，请重新发送。"
    assert "<image_caption>" not in media.IMAGE_INPUT_UNAVAILABLE_NOTICE


def test_has_visual_input_from_urls():
    assert media.has_visual_input(_request(image_urls=["https://example.com/a.png"]))
    assert not media.has_visual_input(_request())


def test_has_visual_input_from_parts():
    request = _request(
        extra_user_content_parts=[{"type": "image_url", "image_url": {}}]
    )
    assert media.has_visual_input(request)


def test_has_visual_input_from_text_only_parts():
    request = _request(extra_user_content_parts=[{"type": "text", "text": "hello"}])
    assert not media.has_visual_input(request)


def test_has_image_caption_from_object_and_dict():
    obj = SimpleNamespace(text=f"prefix {media.IMAGE_CAPTION_MARKER} suffix")
    assert media.has_image_caption([obj])
    assert media.has_image_caption(
        [{"type": "text", "text": media.IMAGE_CAPTION_MARKER}]
    )
    assert not media.has_image_caption([SimpleNamespace(text="plain")])
    assert not media.has_image_caption([])
    assert not media.has_image_caption(None)


def test_image_input_available_prefers_explicit_flag():
    assert not media.image_input_available(_request(image_input_unavailable=True))
    assert media.image_input_available(_request(image_input_unavailable=False))


def test_image_input_available_falls_back_to_visual_input():
    assert media.image_input_available(
        _request(image_urls=["https://example.com/a.png"])
    )
    assert not media.image_input_available(_request())


def test_none_request_is_not_available():
    assert not media.image_input_available(None)
    assert not media.has_visual_input(None)
