"""Plugin attribution must survive the fact that every plugin module is "main".

Every plugin's entry module is literally named ``main``, so ``handler.__module__``
is the same string for all of them and the old prefix check matched nothing.
The source file path has no such ambiguity, and it also works for plugins whose
directory lacks the ``astrbot_plugin_`` prefix (``meme_manager`` is one).
"""

import functools

import pytest

from astrbot.core.plugin_attribution import plugin_of_handler


def _handler_from(file_path: str):
    """Build a handler whose ``__globals__`` carries ``file_path`` as ``__file__``.

    Args:
        file_path: Value to expose as the function's module ``__file__``.

    Returns:
        The defined function object.
    """
    namespace = {"__file__": file_path}
    exec("def handler(): pass", namespace)  # noqa: S102 - controlled input
    return namespace["handler"]


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        # Windows, the case that actually runs here.
        (
            r"C:\Users\x\.astrbot\core\data\plugins\astrbot_plugin_proactive_shadow\main.py",
            "astrbot_plugin_proactive_shadow",
        ),
        # POSIX.
        (
            "/opt/astrbot/data/plugins/astrbot_plugin_livingmemory/main.py",
            "astrbot_plugin_livingmemory",
        ),
        # No astrbot_plugin_ prefix: the prefix check used to miss this one.
        (r"D:\astrbot\data\plugins\meme_manager\main.py", "meme_manager"),
        # An earlier "plugins" segment must not win over the real plugin root.
        (
            r"D:\plugins\astrbot\data\plugins\astrbot_plugin_x\core\helper.py",
            "astrbot_plugin_x",
        ),
    ],
)
def test_plugin_directory_is_taken_from_the_file_path(path, expected):
    assert plugin_of_handler(_handler_from(path)) == expected


@pytest.mark.parametrize(
    "path",
    [
        r"D:\astrbot\main.py",  # not under a plugins directory at all
        r"D:\astrbot\data\plugins",  # "plugins" is the last segment
        "",
    ],
)
def test_unresolvable_paths_return_empty(path):
    assert plugin_of_handler(_handler_from(path)) == ""


def test_callable_without_globals_is_ignored():
    """A C-extension or partial object has no ``__globals__``; that is not fatal."""

    class _Callable:
        def __call__(self) -> None: ...

    assert plugin_of_handler(_Callable()) == ""


def test_non_string_file_value_is_ignored():
    namespace = {"__file__": None}
    exec("def handler(): pass", namespace)  # noqa: S102 - controlled input

    assert plugin_of_handler(namespace["handler"]) == ""


def test_wrapped_handlers_still_resolve():
    """The framework registers bound methods wrapped in functools.partial.

    A partial has no ``__globals__`` and neither does a bound method, so both
    layers have to be unwrapped. An earlier version only handled a bare
    function -- which is not what the framework ever passes -- and resolved
    everything to "".
    """
    namespace = {"__file__": r"C:/inst/core/data/plugins/astrbot_plugin_x/main.py"}
    exec(
        "class P:" + chr(10) + "    def on_group_message(self): pass" + chr(10),
        namespace,
    )
    cls = namespace["P"]

    assert plugin_of_handler(cls().on_group_message) == "astrbot_plugin_x"
    assert (
        plugin_of_handler(functools.partial(cls().on_group_message))
        == "astrbot_plugin_x"
    )
    assert (
        plugin_of_handler(functools.partial(functools.partial(cls().on_group_message)))
        == "astrbot_plugin_x"
    )
