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
    """
    _current_plugin.reset(token)


def current_plugin() -> str:
    """Return the plugin currently being served, or "" when unknown."""
    return _current_plugin.get()
