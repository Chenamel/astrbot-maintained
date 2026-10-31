"""Track which plugin is currently being served.

``Context.llm_generate()`` attributes a call to the plugin that made it, but
the caller's stack is not always reachable: plugins routinely wrap calls in
``asyncio.wait_for``, which schedules the coroutine as its own task and severs
the frame chain. A context variable survives that hop -- every task created
afterwards copies the current context -- so the event dispatcher records the
plugin and the call site reads it back.
"""

from __future__ import annotations

import contextvars
import functools
import json
import time
from collections import defaultdict
from pathlib import Path

from astrbot.core.utils.astrbot_path import get_astrbot_config_path

PLUGIN_MODULE_PREFIX = "astrbot_plugin_"

_current_plugin: contextvars.ContextVar[str] = contextvars.ContextVar(
    "astrbot_current_plugin", default=""
)


def plugin_of_module(module_name: str) -> str:
    """Return the plugin package name for a module path, or "" if not one.

    Args:
        module_name: Dotted path of the module being served, for example the
            main module of a plugin package.

    Returns:
        The first path segment when it names a plugin package, else an empty
        string. Callers stay unattributed rather than risk being mislabelled.
    """
    if not module_name:
        return ""
    root = module_name.split(".", 1)[0]
    return root if root.startswith(PLUGIN_MODULE_PREFIX) else ""


def set_current_plugin(plugin: str) -> contextvars.Token:
    """Mark the current context as serving ``plugin``.

    Args:
        plugin: Plugin package name, or an empty string to clear it.

    Returns:
        The token required to restore the previous value.
    """
    return _current_plugin.set(plugin)


def reset_current_plugin(token: contextvars.Token) -> None:
    """Restore the plugin marker that preceded :func:`set_current_plugin`.

    Args:
        token: Token returned by :func:`set_current_plugin`.

    Notes:
        A generator closed by ``aclose()`` is unwound on a task that did not
        create the token, and ``ContextVar.reset`` refuses a token from another
        context with ``ValueError``. That happens whenever a plugin's handler is
        cancelled mid-flight -- a debounce, a timeout -- and letting it raise
        would replace the real reason for the cancellation with a stack about
        bookkeeping. Restoring is best effort: this context simply has no
        earlier value to go back to.
    """
    try:
        _current_plugin.reset(token)
    except ValueError:
        pass


def plugin_of_handler(handler: object) -> str:
    """Resolve which plugin a handler belongs to, from the file it lives in.

    Module names cannot answer this: every plugin's entry module is literally
    named ``main``, so ``handler.__module__`` is the same string for all of
    them. The source file path is not ambiguous, and it does not care whether
    the plugin directory carries the ``astrbot_plugin_`` prefix.

    Args:
        handler: The handler callable registered by a plugin.

    Returns:
        The plugin directory name, or "" when the handler exposes no
        ``__file__`` or was not loaded from a ``plugins`` directory.
    """
    # The framework registers bound methods as functools.partial(method, self),
    # and a partial carries no __globals__ of its own.
    inner = handler
    while isinstance(inner, functools.partial):
        inner = inner.func
    # A bound method carries no __globals__ either; unwrap it to the function.
    inner = getattr(inner, "__func__", inner)
    handler_globals = getattr(inner, "__globals__", None)
    if not isinstance(handler_globals, dict):
        return ""
    file_path = handler_globals.get("__file__")
    if not isinstance(file_path, str) or not file_path:
        return ""
    parts = Path(file_path).parts
    # Walk backwards: a path may contain an earlier "plugins" segment that is
    # not the plugin root (e.g. a checkout directory named plugins).
    for index in range(len(parts) - 1, -1, -1):
        if parts[index] == "plugins":
            return parts[index + 1] if index + 1 < len(parts) else ""
    return ""


def current_plugin() -> str:
    """Return the plugin currently being served, or "" when unknown."""
    return _current_plugin.get()


_CONFIG_TTL_SECONDS = 60.0
_provider_map_cache: tuple[float, dict[str, tuple[str, ...]]] = (0.0, {})


def _iter_provider_ids(node: object) -> list[str]:
    """Collect provider ids referenced by a parsed plugin config.

    Args:
        node: Any JSON value from a plugin config file.

    Returns:
        Values of keys that look like ``*provider_id``/``*provider`` and hold a
        non-empty string, in document order.
    """
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str) and value and "provider" in key.lower():
                found.append(value)
            else:
                found.extend(_iter_provider_ids(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_iter_provider_ids(item))
    return found


def _provider_plugin_map() -> dict[str, tuple[str, ...]]:
    """Map each configured provider id to the plugins that reference it.

    Reading the plugin configs sidesteps the whole dispatch question: a plugin
    that names a provider for its own calls is exactly the plugin making them,
    no matter how the call reaches the core.

    Returns:
        Provider id -> sorted plugin names. Kept for a short time because this
        runs on the LLM call path and the files rarely change.
    """
    global _provider_map_cache
    now = time.monotonic()
    if now - _provider_map_cache[0] < _CONFIG_TTL_SECONDS:
        return _provider_map_cache[1]

    mapping: defaultdict[str, set[str]] = defaultdict(set)
    try:
        for path in Path(get_astrbot_config_path()).glob("*_config.json"):
            plugin = path.name[: -len("_config.json")]
            if not plugin.startswith(PLUGIN_MODULE_PREFIX):
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                continue
            for provider_id in _iter_provider_ids(data):
                mapping[provider_id].add(plugin)
    except OSError:
        pass

    resolved = {key: tuple(sorted(value)) for key, value in mapping.items()}
    _provider_map_cache = (now, resolved)
    return resolved


def plugins_for_provider(provider_id: str) -> tuple[str, ...]:
    """Return the plugins that configured ``provider_id`` for their own calls.

    Two plugins sharing one provider cannot be told apart from configuration
    alone, so every owner is returned and the caller decides how to present an
    ambiguity instead of silently picking one.

    Args:
        provider_id: Provider id passed to the LLM call.

    Returns:
        Sorted plugin names, empty when the id is not claimed by any plugin.
    """
    if not provider_id:
        return ()
    return _provider_plugin_map().get(provider_id) or ()
