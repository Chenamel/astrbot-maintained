"""Startup argument parsing for the AstrBot entry point.

``main.py`` bootstraps the runtime at import time, so importing it from a test
would start loading the whole core. The parser lives here instead.

Desktop launchers such as AstrBot Launcher start ``python main.py`` with a
fixed argument vector and no way to add flags. ``ASTRBOT_WEBUI_DIR`` gives them
a way to point the core at a separately deployed dashboard dist without that
launcher having to know about it. The same variable is already read by
``astrbot.core.process_restart`` when it rebuilds arguments for a frozen
restart, so the name is a contract shared by both paths.
"""

from __future__ import annotations

import argparse
import os

#: Environment variable a launcher can set when it cannot pass ``--webui-dir``.
WEBUI_DIR_ENV = "ASTRBOT_WEBUI_DIR"


def build_startup_parser(
    env: dict[str, str] | None = None,
) -> argparse.ArgumentParser:
    """Build the argument parser used by ``main.py``.

    An explicit ``--webui-dir`` always wins. Otherwise the environment variable
    is used, which is how a launcher selects a dashboard dist outside the
    ``data/dist`` directory it manages itself. An empty value is treated as
    unset.

    Args:
        env: Environment mapping to read. Defaults to ``os.environ``.

    Returns:
        Parser producing ``webui_dir`` and ``reset_password`` attributes.
    """
    environ = os.environ if env is None else env
    parser = argparse.ArgumentParser(description="AstrBot")
    parser.add_argument(
        "--webui-dir",
        type=str,
        help="Specify the directory path for WebUI static files",
        default=environ.get(WEBUI_DIR_ENV) or None,
    )
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help=(
            "Reset the dashboard initial password on startup and print it in "
            "startup logs"
        ),
    )
    return parser
