"""The core reads plugin extras through one named contract.

These keys are a cross-process contract: plugins write ``_enhance_*`` and the
core reads them. The literals therefore stay exactly as they were -- renaming
them would break every installed plugin in the one way nobody notices. What
these tests protect is the *reading*: a value of the wrong type must degrade to
a default instead of raising in the middle of a reply, and an event that is not
a real event (a test double without ``get_extra``) must read as "unset".

The failure this replaces: ``get_extra("_enhance_owned_quote_image_urls", {})``
followed by ``.get(...)``. A plugin that wrote ``None`` or a string there took
down the whole turn, and nothing in the log said which plugin did it.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from astrbot.api.event import extras


def _event(**values):
    """Return a duck-typed event whose extras are the given keyword values."""
    store = dict(values)

    return SimpleNamespace(
        get_extra=lambda key, default=None: store.get(key, default),
        set_extra=lambda key, value: store.__setitem__(key, value),
        store=store,
    )


def _empty():
    """A test double with no extras API at all."""
    return SimpleNamespace()


# --------------------------------------------------------------------------
# The literals are frozen
# --------------------------------------------------------------------------


def test_every_key_is_the_original_literal():
    """Renaming one of these silently disables a feature in every plugin."""
    assert extras.ACTIVE_REPLY_TOKEN == "_enhance_active_reply_token"
    assert extras.ACTIVE_REPLY_TRIGGERED == "_enhance_active_reply_triggered"
    assert extras.VISUAL_REQUESTED == "_enhance_visual_requested"
    assert extras.VISUAL_UNAVAILABLE == "_enhance_visual_unavailable"
    assert extras.OWNED_IMAGE_URLS == "_enhance_owned_image_urls"
    assert extras.OWNED_QUOTE_IMAGE_URLS == "_enhance_owned_quote_image_urls"
    assert extras.FOLLOWUP_DIRECT == "_enhance_followup_direct"
    assert extras.FOLLOWUP_TASK == "_enhance_followup_task"
    assert extras.PROACTIVE_LIGHTWEIGHT == "_enhance_proactive_lightweight"


def test_the_core_no_longer_spells_the_keys_itself():
    """One home for the vocabulary, or it drifts again.

    ``astrbot/core`` reading a literal means the core knows one particular
    plugin's private naming -- the thing this module exists to stop.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "astrbot" / "core"
    offenders = [
        str(path.relative_to(root.parent))
        for path in root.rglob("*.py")
        if "_enhance_" in path.read_text(encoding="utf-8", errors="replace")
    ]

    assert not offenders, f"core still reads the private keys directly: {offenders}"


# --------------------------------------------------------------------------
# Flags: only a real True counts
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [(True, True), (False, False), (1, False), ("true", False), (None, False)],
)
def test_a_flag_is_only_true_when_it_is_true(value, expected):
    """The surrounding conditions use ``is True``; a truthy 1 must not pass.

    Guessing here would silently disagree with plugins that treat the value as
    a plain boolean, and the caller cannot tell the difference afterwards.
    """
    event = _event(**{extras.VISUAL_REQUESTED: value})

    assert extras.visual_requested(event) is expected


def test_active_reply_accepts_any_non_empty_token():
    """The token is an opaque string, not a boolean: its presence means "mine"."""
    assert extras.is_active_reply(_event(**{extras.ACTIVE_REPLY_TOKEN: "abc"}))

    for empty in ("", None, 0):
        assert not extras.is_active_reply(_event(**{extras.ACTIVE_REPLY_TOKEN: empty}))


def test_text_readers_return_empty_string_for_wrong_types():
    assert extras.followup_task(_event(**{extras.FOLLOWUP_TASK: 42})) == ""
    assert extras.followup_task(_event(**{extras.FOLLOWUP_TASK: "写脚本"})) == "写脚本"


# --------------------------------------------------------------------------
# Collections: wrong shapes are dropped, not raised on
# --------------------------------------------------------------------------


def test_a_single_url_string_is_one_url_not_a_character_list():
    """``extend("http://...")`` would append every character as an image."""
    urls = extras.owned_image_urls(_event(**{extras.OWNED_IMAGE_URLS: "http://x/a.png"}))

    assert urls == ["http://x/a.png"]


@pytest.mark.parametrize("bad", [None, 0, {}, [1, 2], ["ok", None, ""]])
def test_a_malformed_url_list_is_filtered(bad):
    urls = extras.owned_image_urls(_event(**{extras.OWNED_IMAGE_URLS: bad}))

    assert urls == [] or all(isinstance(url, str) and url for url in urls)


def test_quote_urls_survive_a_value_that_is_not_a_mapping():
    """This is the crash that motivated the module: ``.get()`` on a string."""
    for bad in (None, "nope", 42, ["a"]):
        assert extras.owned_quote_image_urls(
            _event(**{extras.OWNED_QUOTE_IMAGE_URLS: bad})
        ) == {}


def test_quote_urls_are_keyed_by_message_id_and_cleaned():
    value = {"1": ["http://x/a.png"], "2": "http://x/b.png", "3": [None]}
    urls = extras.owned_quote_image_urls(_event(**{extras.OWNED_QUOTE_IMAGE_URLS: value}))

    assert urls == {"1": ["http://x/a.png"], "2": ["http://x/b.png"]}


# --------------------------------------------------------------------------
# Events without the extras API
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reader,expected",
    [
        (extras.active_reply_token, ""),
        (extras.is_active_reply, False),
        (extras.active_reply_triggered, False),
        (extras.visual_requested, False),
        (extras.visual_unavailable, False),
        (extras.owned_image_urls, []),
        (extras.owned_quote_image_urls, {}),
        (extras.followup_direct, False),
        (extras.followup_task, ""),
        (extras.proactive_lightweight, False),
    ],
)
def test_an_event_without_get_extra_reads_as_unset(reader, expected):
    """Runner events are only sometimes real events; neither may crash."""
    assert reader(_empty()) == expected
    assert reader(None) == expected


def test_a_raising_getter_is_treated_as_unset():
    class _Broken:
        def get_extra(self, key, default=None):
            raise RuntimeError("event is half-built")

    assert extras.is_active_reply(_Broken()) is False
    assert extras.owned_quote_image_urls(_Broken()) == {}


def test_set_visual_unavailable_writes_the_original_key():
    event = _event()

    extras.set_visual_unavailable(event, True)

    assert event.store == {"_enhance_visual_unavailable": True}
    assert extras.visual_unavailable(event) is True


def test_set_visual_unavailable_tolerates_a_read_only_event():
    """A marker that cannot be written must not abort the image stage."""
    extras.set_visual_unavailable(_empty(), True)
    extras.set_visual_unavailable(None, True)
