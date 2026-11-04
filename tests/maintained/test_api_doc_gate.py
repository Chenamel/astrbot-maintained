"""Mechanical enforcement of the public-surface documentation gate.

The ``project_rules`` document (§9) requires that every module this fork adds
under ``astrbot/api/`` is usable by the community: a module docstring, an explicit
``__all__`` that matches the contract, a docstring on every exported symbol, a
``#:`` comment on every exported constant -- and no public-looking definition
that is absent from ``__all__`` ("wild private definitions").

Upstream modules under ``astrbot/api/`` are frozen and deliberately excluded.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Modules this fork owns. Upstream modules are frozen (see test_api_frozen.py).
OWNED_MODULES = [
    "astrbot.api._bridge",
    "astrbot.api.content",
    "astrbot.api.delivery",
    "astrbot.api.embedding",
    "astrbot.api.media",
    "astrbot.api.permissions",
    "astrbot.api.proactive",
    "astrbot.api.runtime",
    "astrbot.api.turns",
]

#: Modules that are internal by contract (api-contract.md §2): they must stay
#: documented, but they are allowed to hold non-exported helpers.
INTERNAL_MODULES = {"astrbot.api._bridge"}

#: Public modules: everything else this fork owns.
PUBLIC_MODULES = [name for name in OWNED_MODULES if name not in INTERNAL_MODULES]


def _module_path(dotted: str) -> Path:
    return REPO_ROOT / Path(*dotted.split(".")).with_suffix(".py")


def _module_source(dotted: str) -> str:
    path = _module_path(dotted)
    if path.is_file():
        return path.read_text(encoding="utf-8")
    package = REPO_ROOT / Path(*dotted.split(".")) / "__init__.py"
    return package.read_text(encoding="utf-8")


def _imported_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _declared_all(tree: ast.Module) -> list[str] | None:
    """Return the literal contents of ``__all__``, or ``None`` when absent.

    Handles both ``__all__ = [...]`` and the annotated ``__all__: list[str] = [...]``
    form.
    """
    for node in tree.body:
        target = None
        value = None
        if isinstance(node, ast.Assign):
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        if isinstance(target, ast.Name) and target.id == "__all__":
            if value is None:
                return []
            return [element.value for element in value.elts]
    return None


@pytest.mark.parametrize("dotted", OWNED_MODULES)
def test_module_has_docstring(dotted: str) -> None:
    assert ast.get_docstring(ast.parse(_module_source(dotted))), (
        f"{dotted} has no module docstring (fork API doc gate)"
    )


@pytest.mark.parametrize("dotted", OWNED_MODULES)
def test_module_declares_all(dotted: str) -> None:
    assert _declared_all(ast.parse(_module_source(dotted))) is not None, (
        f"{dotted} has no explicit __all__ (fork API doc gate)"
    )


@pytest.mark.parametrize("dotted", OWNED_MODULES)
def test_all_names_are_importable(dotted: str) -> None:
    module = importlib.import_module(dotted)
    missing = [name for name in module.__all__ if not hasattr(module, name)]
    assert not missing, f"{dotted} exports names that do not exist: {missing}"


@pytest.mark.parametrize("dotted", OWNED_MODULES)
def test_public_symbols_have_docstrings(dotted: str) -> None:
    tree = ast.parse(_module_source(dotted))
    exported = set(_declared_all(tree) or [])
    undocumented = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in exported and not ast.get_docstring(node):
                undocumented.append(node.name)
    assert not undocumented, (
        f"{dotted} exports undocumented callables: {undocumented} (fork API doc gate)"
    )


@pytest.mark.parametrize("dotted", PUBLIC_MODULES)
def test_no_wild_public_definitions(dotted: str) -> None:
    """No public-looking module-level name may exist outside __all__."""
    source = _module_source(dotted)
    tree = ast.parse(source)
    exported = set(_declared_all(tree) or [])
    imported = _imported_names(tree)
    offenders: list[str] = []
    for node in tree.body:
        targets: list[str] = []
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            targets = [node.name]
        for name in targets:
            if name.startswith("_") or name in imported or name in exported:
                continue
            offenders.append(name)
    assert not offenders, (
        f"{dotted} has public-looking names outside __all__: {offenders} "
        "(fork API doc gate forbids wild private definitions)"
    )


def test_internal_bridge_exports_nothing() -> None:
    """The internal bridge must stay internal: an empty __all__ and no exports."""
    module = importlib.import_module("astrbot.api._bridge")
    assert module.__all__ == [], "astrbot.api._bridge must not export anything"
    documentation = (module.__doc__ or "").replace("*", "")
    assert "not part of the public API" in documentation, (
        "astrbot.api._bridge must document itself as internal"
    )


@pytest.mark.parametrize("dotted", OWNED_MODULES)
def test_exported_constants_have_marker_comments(dotted: str) -> None:
    """Every exported non-callable must carry a ``#:`` comment above it."""
    lines = _module_source(dotted).splitlines()
    tree = ast.parse("\n".join(lines))
    exported = set(_declared_all(tree) or [])
    unmarked: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name) or target.id not in exported:
                continue
            index = node.lineno - 2
            while index >= 0 and not lines[index].strip():
                index -= 1
            if index < 0 or not lines[index].lstrip().startswith("#:"):
                unmarked.append(target.id)
    assert not unmarked, (
        f"{dotted} exports constants without a '#:' comment: {unmarked} (fork API doc gate)"
    )
