"""Behaviour of the additive direct-turn module under degradation.

The baseline core has no direct-turn support, so these tests pin the safe
defaults. Assertions that depend on availability are expressed relative to
``turns.available()`` so they keep passing once the core patches are restored.
"""

from types import SimpleNamespace

import astrbot.api.turns as turns


def _event(**extras):
    store = dict(extras)

    def get_extra(key, default=None):
        return store.get(key, default)

    return SimpleNamespace(get_extra=get_extra)


def test_module_is_importable_and_available_is_boolean():
    assert isinstance(turns.available(), bool)


def test_is_current_never_raises_on_foreign_object():
    assert isinstance(turns.is_current(object()), bool)
    assert isinstance(turns.is_current(_event()), bool)


def test_is_current_reports_current_when_support_absent():
    if turns.available():
        return
    assert turns.is_current(_event()) is True


def test_mark_sent_is_safe_to_call():
    turns.mark_sent(object())
    turns.mark_sent(_event())


def test_turn_version_reads_extra():
    assert turns.turn_version(_event(_direct_turn_version=3)) == 3
    assert turns.turn_version(_event(_direct_turn_version="3")) is None
    assert turns.turn_version(_event()) is None


def test_merged_text_reads_extra():
    assert turns.merged_text(_event(_direct_turn_text="a\nb")) == "a\nb"
    assert turns.merged_text(_event(_direct_turn_text=123)) == ""
    assert turns.merged_text(_event()) == ""


def test_merged_image_urls_reads_and_filters_extra():
    assert turns.merged_image_urls(_event(_direct_turn_image_urls=["u1", "u2"])) == [
        "u1",
        "u2",
    ]
    assert turns.merged_image_urls(_event(_direct_turn_image_urls=["u1", 2, None])) == [
        "u1"
    ]
    assert turns.merged_image_urls(_event(_direct_turn_image_urls="u1")) == []
    assert turns.merged_image_urls(_event()) == []


def test_reset_reports_false_when_support_absent():
    if turns.available():
        return
    assert turns.reset("umo") is False
    assert turns.reset_all() is False


def test_reset_tolerates_absent_coordinator_methods():
    assert isinstance(turns.reset("umo"), bool)
    assert isinstance(turns.reset_all(), bool)
