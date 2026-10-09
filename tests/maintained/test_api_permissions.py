"""Behaviour of the additive permission helpers.

The security invariant under test: :func:`execution_denial` must never degrade
into an unconditional allow. A non-administrator is refused whether or not the
core-side policy engine is installed.
"""

from types import SimpleNamespace

import astrbot.api.permissions as permissions


def _event(sender_id="10001"):
    return SimpleNamespace(get_sender_id=lambda: sender_id)


def _event_without_getter(sender_id="10001"):
    sender = SimpleNamespace(user_id=sender_id)
    return SimpleNamespace(message_obj=SimpleNamespace(sender=sender))


def test_available_is_boolean():
    assert isinstance(permissions.available(), bool)


def test_is_admin_matches_string_ids():
    config = {"admins_id": ["10001", "10002"]}
    assert permissions.is_admin(_event("10001"), config)
    assert not permissions.is_admin(_event("99999"), config)


def test_is_admin_accepts_scalar_and_int_entries():
    assert permissions.is_admin(_event("10001"), {"admins_id": "10001"})
    assert permissions.is_admin(_event("10001"), {"admins_id": [10001]})


def test_is_admin_handles_missing_config_and_sender():
    assert not permissions.is_admin(_event("10001"), None)
    assert not permissions.is_admin(_event("10001"), {})
    assert not permissions.is_admin(_event(""), {"admins_id": ["10001"]})
    assert not permissions.is_admin(object(), {"admins_id": ["10001"]})


def test_is_admin_reads_sender_from_message_obj():
    assert permissions.is_admin(
        _event_without_getter("10001"), {"admins_id": ["10001"]}
    )


def test_non_admin_is_always_denied():
    config = {"admins_id": ["10001"]}
    reason = permissions.execution_denial(_event("99999"), config)
    assert reason is not None
    assert isinstance(reason, str)
    assert reason.strip()


def test_admin_is_not_denied_by_fallback_layer():
    if permissions.available():
        return
    config = {"admins_id": ["10001"]}
    assert permissions.execution_denial(_event("10001"), config) is None


def test_denial_never_raises_on_foreign_objects():
    reason = permissions.execution_denial(object(), None)
    assert reason is None or isinstance(reason, str)


def test_denial_messages_are_declared_constants():
    assert permissions.EXECUTION_NOT_AUTHORIZED.strip()
    assert "administrator" in permissions.EXECUTION_NOT_AUTHORIZED
