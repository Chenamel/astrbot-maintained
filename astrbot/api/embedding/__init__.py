"""Embedding provider type, for plugins that work with vector storage.

Public surface (see ``docs/maintained/api-contract.md``):

- :data:`EmbeddingProvider`
- :func:`available`
- :func:`is_embedding_provider`

When the core does not provide the type the attribute is ``None`` and the
helper returns ``False``, so importing this module never fails.
"""

from __future__ import annotations

from typing import Any

from astrbot.api._bridge import resolve

__all__ = [
    "EmbeddingProvider",
    "available",
    "is_embedding_provider",
]

_MODULE = "astrbot.core.provider.provider"

#: Embedding provider type, or ``None`` when the core does not provide it.
EmbeddingProvider: Any = resolve(_MODULE, "EmbeddingProvider", None)


def available() -> bool:
    """Return whether the core-side embedding provider type is installed."""
    return EmbeddingProvider is not None


def is_embedding_provider(candidate: Any) -> bool:
    """Return whether ``candidate`` is an embedding provider.

    Args:
        candidate: The object to inspect.

    Returns:
        ``True`` only when the core type is available and matches.
    """
    return EmbeddingProvider is not None and isinstance(candidate, EmbeddingProvider)
