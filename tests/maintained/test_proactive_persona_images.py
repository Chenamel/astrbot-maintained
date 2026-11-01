"""Pictures on the proactive path.

The wording step of a proactive reply used to send no picture at all while the
judge had one, which is how the bot answered "补个截图或者模组名吧" to somebody
who had posted the screenshot nineteen seconds earlier.

The pipeline that fixes it has three outcomes, and each has its own way of being
wrong in a live group:

* a provider that declares image input must receive the picture, compressed and
  localised, exactly like the @-mention path does;
* a text-only provider must receive a caption instead of a file path it cannot
  read -- sending the path anyway makes the request fail, not degrade;
* when neither is possible the model must be told to leave the topic alone.
  Asking for the picture again is the bug being fixed; inventing what it shows
  would be worse, so the note forbids both.
"""

import types

import pytest

from astrbot.core import astr_main_agent, astr_main_agent_quote, proactive_persona
from astrbot.core.pipeline.process_stage.method.agent_sub_stages import image_input
from astrbot.core.provider.entities import IMAGE_CAPTION_MARKER, ProviderRequest

CAPTION_ID = "zhipu/glm-4.6v-flash"


def _context(settings: dict):
    """A plugin context that only knows how to hand back provider settings."""
    return types.SimpleNamespace(
        get_config=lambda umo=None: {"provider_settings": settings},
    )


def _event():
    """The event carries nothing these tests need beyond the local-file hook."""
    return types.SimpleNamespace(
        unified_msg_origin="default:GroupMessage:1",
        track_temporary_local_file=lambda path: None,
    )


def _request(prompt: str = "[某人/12:00:00] [Image]", images=("https://cdn/x.jpg",)):
    return ProviderRequest(prompt=prompt, image_urls=list(images))


def _stub_preparation(monkeypatch, prepared: str | None = "/tmp/prepared.jpg"):
    """Record that preparation ran and rewrite the refs the way core would."""
    seen: dict = {}

    async def _fake(req, event, **kwargs):
        seen["kwargs"] = kwargs
        req.image_urls = [prepared] if prepared else []

    monkeypatch.setattr(image_input, "prepare_request_images", _fake)
    return seen


def _stub_modality(monkeypatch, supports: bool):
    monkeypatch.setattr(
        astr_main_agent_quote,
        "_provider_supports_modality",
        lambda provider, modality: supports,
    )


def _caption_parts(req: ProviderRequest) -> list[str]:
    return [
        str(getattr(part, "text", ""))
        for part in req.extra_user_content_parts
        if IMAGE_CAPTION_MARKER in str(getattr(part, "text", ""))
    ]


@pytest.mark.asyncio
async def test_a_request_without_pictures_does_no_work(monkeypatch):
    """The common case must stay free: no config read, no preparation."""
    seen = _stub_preparation(monkeypatch)
    req = _request(images=())

    await proactive_persona._prepare_images(
        _context({}), _event(), req, types.SimpleNamespace()
    )

    assert seen == {}
    assert req.image_urls == []
    assert req.system_prompt == ""


@pytest.mark.asyncio
async def test_a_vision_provider_keeps_the_prepared_picture(monkeypatch):
    """Same picture the @-mention path sends: compressed and localised."""
    seen = _stub_preparation(monkeypatch)
    _stub_modality(monkeypatch, supports=True)
    req = _request()

    await proactive_persona._prepare_images(
        _context({"image_compress_enabled": True}), _event(), req, object()
    )

    assert req.image_urls == ["/tmp/prepared.jpg"]
    assert seen["kwargs"]["enabled"] is True
    assert seen["kwargs"]["max_size"] == seen["kwargs"]["montage_max_size"]
    assert req.system_prompt == ""


@pytest.mark.asyncio
async def test_a_text_only_provider_gets_a_caption_not_a_file_path(monkeypatch):
    """A provider that cannot read pixels must not be handed a path."""
    _stub_preparation(monkeypatch)
    _stub_modality(monkeypatch, supports=False)

    async def _fake_caption(provider_id, cfg, image_urls, context):
        assert provider_id == CAPTION_ID
        assert image_urls == ["/tmp/prepared.jpg"]
        return "一张配电箱照片，接线端子松了"

    monkeypatch.setattr(astr_main_agent, "_request_img_caption", _fake_caption)
    req = _request()

    await proactive_persona._prepare_images(
        _context({"default_image_caption_provider_id": CAPTION_ID}),
        _event(),
        req,
        object(),
    )

    assert req.image_urls == []
    parts = _caption_parts(req)
    assert len(parts) == 1
    assert "一张配电箱照片" in parts[0]
    assert req.system_prompt == ""


@pytest.mark.asyncio
async def test_without_a_caption_provider_the_model_is_told_to_drop_it(monkeypatch):
    """No vision anywhere: neither ask again nor describe what cannot be seen."""
    _stub_preparation(monkeypatch)
    _stub_modality(monkeypatch, supports=False)
    req = _request()

    await proactive_persona._prepare_images(
        _context({"default_image_caption_provider_id": ""}), _event(), req, object()
    )

    assert req.image_urls == []
    assert req.system_prompt.endswith(proactive_persona._NO_VISUAL_NOTE)
    assert "[Image]" in req.prompt


@pytest.mark.asyncio
async def test_a_failed_caption_still_leaves_a_sendable_request(monkeypatch):
    """Captioning is an upgrade; losing it must not lose the reply."""
    _stub_preparation(monkeypatch)
    _stub_modality(monkeypatch, supports=False)

    async def _boom(provider_id, cfg, image_urls, context):
        raise RuntimeError("provider down")

    monkeypatch.setattr(astr_main_agent, "_request_img_caption", _boom)
    req = _request()

    await proactive_persona._prepare_images(
        _context({"default_image_caption_provider_id": CAPTION_ID}),
        _event(),
        req,
        object(),
    )

    assert req.image_urls == []
    assert _caption_parts(req) == []
    assert req.system_prompt.endswith(proactive_persona._NO_VISUAL_NOTE)


@pytest.mark.asyncio
async def test_a_prompt_without_a_picture_mention_gets_no_note(monkeypatch):
    """The note is only for a conversation that actually refers to a picture."""
    _stub_preparation(monkeypatch, prepared=None)
    _stub_modality(monkeypatch, supports=False)
    req = _request(prompt="[某人/12:00:00] 今天这局怎么打")

    await proactive_persona._prepare_images(
        _context({"default_image_caption_provider_id": ""}), _event(), req, object()
    )

    assert req.image_urls == []
    assert req.system_prompt == ""
