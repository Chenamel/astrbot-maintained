"""The launcher-friendly WebUI directory fallback.

AstrBot Launcher starts ``python main.py`` with a fixed argument vector, so the
fork's own dashboard dist cannot be selected with ``--webui-dir``. The core
reads ``ASTRBOT_WEBUI_DIR`` as a fallback. These tests pin the precedence and
the shared variable name without importing ``main.py``, which bootstraps the
runtime at import time.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_startup_args():
    spec = importlib.util.spec_from_file_location(
        "startup_args", REPO_ROOT / "startup_args.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


startup_args = _load_startup_args()


def test_no_source_yields_no_explicit_dir() -> None:
    args = startup_args.build_startup_parser(env={}).parse_args([])
    assert args.webui_dir is None


def test_environment_variable_is_the_fallback() -> None:
    env = {startup_args.WEBUI_DIR_ENV: "/instances/core/data/dist_maintained"}
    args = startup_args.build_startup_parser(env=env).parse_args([])
    assert args.webui_dir == "/instances/core/data/dist_maintained"


def test_explicit_flag_wins_over_environment() -> None:
    env = {startup_args.WEBUI_DIR_ENV: "/from/env"}
    args = startup_args.build_startup_parser(env=env).parse_args(
        ["--webui-dir", "/from/flag"]
    )
    assert args.webui_dir == "/from/flag"


def test_empty_environment_value_is_unset() -> None:
    args = startup_args.build_startup_parser(
        env={startup_args.WEBUI_DIR_ENV: ""}
    ).parse_args([])
    assert args.webui_dir is None


def test_real_environ_is_the_default(monkeypatch) -> None:
    monkeypatch.setenv(startup_args.WEBUI_DIR_ENV, "/from/process/env")
    args = startup_args.build_startup_parser().parse_args([])
    assert args.webui_dir == "/from/process/env"


def test_reset_password_flag_is_unchanged() -> None:
    parser = startup_args.build_startup_parser(env={})
    assert parser.parse_args([]).reset_password is False
    assert parser.parse_args(["--reset-password"]).reset_password is True


def test_variable_name_matches_the_restart_path() -> None:
    """A frozen restart rebuilds --webui-dir from the same variable."""
    text = (REPO_ROOT / "astrbot" / "core" / "process_restart.py").read_text(
        encoding="utf-8"
    )
    assert f'"{startup_args.WEBUI_DIR_ENV}"' in text
    assert (REPO_ROOT / "main.py").read_text(encoding="utf-8").count(
        "startup_args.build_startup_parser()"
    ) == 1
