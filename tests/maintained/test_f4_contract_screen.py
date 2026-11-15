"""The F4 contract screen must flag removed API symbols without touching git state."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "maintained"
    / "tools"
    / "f4_contract_screen.py"
)


def _load():
    spec = importlib.util.spec_from_file_location(
        "f4_contract_screen_under_test", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_screen_flags_a_removed_api_symbol(tmp_path, capsys, monkeypatch):
    repo = tmp_path
    api = repo / "astrbot" / "api" / "__init__.py"
    api.parent.mkdir(parents=True)
    api.write_text(
        "def alpha(a, b):\n    pass\n\nclass Beta:\n    pass\n", encoding="utf-8"
    )
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(
        repo,
        "-c",
        "user.name=test",
        "-c",
        "user.email=t@example.com",
        "commit",
        "-qm",
        "baseline",
    )
    _git(repo, "tag", "baseline/v9.9.9")

    api.write_text("class Beta:\n    pass\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(
        repo,
        "-c",
        "user.name=test",
        "-c",
        "user.email=t@example.com",
        "commit",
        "-qm",
        "drop alpha",
    )

    mod = _load()
    assert mod.latest_baseline(repo) == "baseline/v9.9.9"
    monkeypatch.setattr(
        sys,
        "argv",
        ["f4_contract_screen.py", "--repo", str(repo), "--target", "HEAD"],
    )
    mod.main()
    report = json.loads(capsys.readouterr().out)
    assert report["base_ref"] == "baseline/v9.9.9"
    assert any(
        issue["symbol"] == "alpha" and issue["issue"] == "removed_in_target"
        for issue in report["issues"]
    )


def test_extract_signatures_sees_reexports():
    mod = _load()
    sigs = mod.extract_signatures(
        "from .extractor import extract_quoted_message_images\n"
        "async def go(a, *, b=1):\n    pass\n"
    )
    assert sigs["extract_quoted_message_images"]["kind"] == "reexport"
    assert sigs["go"]["pos_args"] == ["a"]
    assert sigs["go"]["kw_args"] == ["b"]
