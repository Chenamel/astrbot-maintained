"""Behaviour of the additive embedding module under degradation."""

from types import SimpleNamespace

import astrbot.api.embedding as embedding


def test_available_is_boolean():
    assert isinstance(embedding.available(), bool)


def test_helper_is_false_when_type_absent():
    if embedding.available():
        return
    assert embedding.is_embedding_provider(SimpleNamespace()) is False


def test_helper_tolerates_foreign_objects():
    for candidate in (None, object(), "provider", 0):
        assert isinstance(embedding.is_embedding_provider(candidate), bool)


def test_type_is_exposed_as_attribute():
    assert hasattr(embedding, "EmbeddingProvider")
