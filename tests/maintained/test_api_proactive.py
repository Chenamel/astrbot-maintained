"""Behaviour of the additive proactive module.

The invariant under test: the proactive-reply switch stays disabled and no
function in this module can enable it.
"""

from types import SimpleNamespace

import astrbot.api.proactive as proactive


def _event(**extras):
    store = dict(extras)

    def get_extra(key, default=None):
        return store.get(key, default)

    return SimpleNamespace(get_extra=get_extra)


def test_switch_is_always_reported_disabled():
    assert proactive.proactive_switch_is_disabled() is True


def test_module_exposes_no_enable_entry_point():
    for symbol in proactive.__all__:
        assert "enable" not in symbol
        assert "enable" not in str(getattr(proactive, symbol)).lower()


def test_available_is_boolean():
    assert isinstance(proactive.available(), bool)


def test_classifier_is_false_when_core_absent():
    if proactive.available():
        return
    assert proactive.is_lightweight_proactive(_event()) is False


def test_classifier_tolerates_foreign_objects():
    assert isinstance(proactive.is_lightweight_proactive(object()), bool)
    assert isinstance(proactive.is_lightweight_proactive(None), bool)
