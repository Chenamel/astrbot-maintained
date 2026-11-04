"""Where the maintained fork keeps its documentation.

The repository has two documentation trees, and they are read by different
people:

``docs/``
    Published. Written for users of the fork and for plugin developers who want
    to build on it -- "what changed, how do I plug in".
``.internal/``
    Maintainer-only, excluded by ``.gitignore``. Written for whoever picks the
    work up next -- "where did we stop, why is this file like this". These
    documents name the operator's instance path, accounts and private plugins,
    so they must never be published.

A document may move between the two trees without its readers noticing, so
nothing should spell out ``"docs/maintained/..."`` or
``".internal/notes/..."`` directly. Ask this module instead:

    >>> import doc_paths
    >>> doc_paths.read("inventory")           # None when the doc is not here
    >>> doc_paths.path("project_rules")       # None when the doc is not here

Every document is declared once, with its candidate locations in lookup order.
Because ``.internal/`` is not published, a check that reads such a document must
treat ``None`` as a legitimate state rather than an error -- a fresh clone of the
public repository simply does not have the file. Anything the build must be able
to prove therefore belongs in code, not in a document: see
``maintained/p11_deviations.py::PROTECTED_RED_LINES``.
"""

from __future__ import annotations

from pathlib import Path

#: Repository root, resolved from this file (``maintained/doc_paths.py``).
REPO_ROOT = Path(__file__).resolve().parents[1]

#: Declared documents, each with the locations it may occupy, in lookup order.
#: The first entry is where the document lives today; the later ones are earlier
#: homes kept so that a working tree mid-migration still resolves instead of
#: reporting the document as missing.
DOCUMENTS: dict[str, tuple[str, ...]] = {
    "inventory": (
        ".internal/notes/inventory.md",
        "docs/maintained/inventory.md",
    ),
    "project_rules": (
        ".internal/rules/project_rules.md",
        "docs/maintained/project_rules.md",
    ),
}


def path(name: str) -> Path | None:
    """Return the first existing location of a declared document.

    Args:
        name: Key in :data:`DOCUMENTS`, e.g. ``"inventory"``.

    Returns:
        The absolute path of the first candidate that exists, or ``None`` when
        the document is absent from this working tree. Absence is expected for
        maintainer-only documents in a fresh clone of the public repository.

    Raises:
        KeyError: ``name`` is not declared in :data:`DOCUMENTS`.
    """
    for relative in DOCUMENTS[name]:
        candidate = REPO_ROOT / relative
        if candidate.is_file():
            return candidate
    return None


def read(name: str) -> str | None:
    """Return a declared document's text, or ``None`` when it is absent.

    Args:
        name: Key in :data:`DOCUMENTS`, e.g. ``"project_rules"``.

    Returns:
        The file's text, or ``None`` when no candidate exists.

    Raises:
        KeyError: ``name`` is not declared in :data:`DOCUMENTS`.
    """
    resolved = path(name)
    if resolved is None:
        return None
    return resolved.read_text(encoding="utf-8")
