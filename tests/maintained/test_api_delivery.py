"""Behaviour of the additive delivery helpers under degradation."""

from types import SimpleNamespace

import astrbot.api.delivery as delivery


def test_available_is_boolean():
    assert isinstance(delivery.available(), bool)


def test_code_delivery_failure_is_non_empty_string():
    assert isinstance(delivery.CODE_DELIVERY_FAILURE, str)
    assert delivery.CODE_DELIVERY_FAILURE.strip()


def test_code_task_spec_returns_none_when_policy_absent():
    if delivery.available():
        return
    assert delivery.code_task_spec(SimpleNamespace()) is None


def test_code_task_spec_tolerates_foreign_object():
    assert delivery.code_task_spec(object()) is None


def test_has_code_delivery_is_false_when_policy_absent():
    if delivery.available():
        return
    assert delivery.has_code_delivery("no code here", "python") is False


def test_has_code_delivery_never_raises():
    assert isinstance(delivery.has_code_delivery("", ""), bool)
