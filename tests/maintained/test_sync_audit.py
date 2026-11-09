"""Regression tests for the upstream sync audit.

The audit is only useful if it still catches the four failure modes that
actually happened during the 4.29.4 bump. These tests build tiny fixtures and
assert the audit reports them, plus a few false-positive guards.
"""

from __future__ import annotations

import json
from pathlib import Path

from tools import sync_audit as audit


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_signatures_detects_removed_kwarg(monkeypatch):
    """A kwarg dropped upstream must appear as a signature change."""
    old = "def prepare(image, *, max_size, quality=80):\n    pass\n"
    new = "def prepare(image, *, max_size):\n    pass\n"
    monkeypatch.setattr(
        audit, "show", lambda ref, path: old if ref == audit.OLD_BASE else new
    )

    changed = audit.changed_signatures(["astrbot/core/utils/media.py"])
    sig = changed["astrbot.core.utils.media"]["prepare"]
    assert sig is not None
    assert "quality" not in sig.names
    assert "max_size" in sig.names


def test_signatures_marks_removed_symbol(monkeypatch):
    """A callable deleted upstream is recorded with a None signature."""
    old = "def gone(x):\n    pass\n"
    monkeypatch.setattr(
        audit, "show", lambda ref, path: old if ref == audit.OLD_BASE else ""
    )
    changed = audit.changed_signatures(["astrbot/core/utils/media.py"])
    assert changed["astrbot.core.utils.media"]["gone"] is None


def test_s1_reports_stale_kwarg(tmp_path, monkeypatch):
    """A fork call site passing a removed kwarg must be BLOCK."""
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    _write(
        tmp_path / "astrbot" / "core" / "caller.py",
        "from astrbot.core.utils.media import prepare\n"
        "result = prepare('x', max_size=1, quality=90)\n",
    )
    changed = {
        "astrbot.core.utils.media": {
            "prepare": audit.Signature(frozenset({"max_size"}), 1, False)
        }
    }
    findings = audit.check_s1(changed)
    assert any(
        item.level == audit.BLOCK and "quality" in item.evidence for item in findings
    )


def test_s1_ignores_fork_kept_module(tmp_path, monkeypatch):
    """A symbol removed upstream but deliberately kept by the fork is fine."""
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    _write(
        tmp_path / "astrbot" / "core" / "caller.py",
        "from astrbot.core.legacy import kept\nkept()\n",
    )
    _write(tmp_path / "astrbot" / "core" / "legacy.py", "def kept():\n    pass\n")
    findings = audit.check_s1({"astrbot.core.legacy": {"kept": None}})
    assert not [item for item in findings if item.level == audit.BLOCK]


def test_s4_flags_local_import_not_bare_package(tmp_path, monkeypatch):
    """Bare npm packages resolve via node_modules; local paths must exist."""
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    _write(
        tmp_path / "dashboard" / "src" / "views" / "Page.vue",
        "import Icon from '@lucide/vue'\n"
        "import Missing from '@/components/Missing.vue'\n",
    )
    findings = audit.check_s4()
    blocked = [item for item in findings if item.level == audit.BLOCK]
    assert len(blocked) == 1
    assert "Missing.vue" in blocked[0].evidence
    assert all("@lucide/vue" not in item.evidence for item in findings)


def test_s5_reports_unregistered_bundle(tmp_path, monkeypatch):
    """A locale bundle on disk but not imported must be BLOCK."""
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    base = tmp_path / "dashboard" / "src" / "i18n" / "locales" / "zh-CN"
    _write(base / "features" / "calls.json", '{"quick": {"today": "today"}}')
    _write(base / "features" / "chat.json", '{"a": "b"}')
    _write(
        base / "index.ts",
        "import zhCNChat from './features/chat.json';\n"
        "export default { features: { chat: zhCNChat } };\n",
    )
    findings = audit.check_s5()
    assert any(
        item.level == audit.BLOCK and "calls.json" in item.evidence for item in findings
    )


def test_s7_reports_missing_local_module(tmp_path, monkeypatch):
    """An import of a module upstream deleted must be BLOCK."""
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    _write(
        tmp_path / "astrbot" / "core" / "caller.py",
        "from astrbot.core.utils.gone_module import thing\n",
    )
    findings = audit.check_s7()
    assert any(
        item.level == audit.BLOCK and "gone_module" in item.evidence
        for item in findings
    )


def test_s8_reports_removed_api_export(tmp_path, monkeypatch):
    """Dropping an upstream API export breaks plugins and must be BLOCK."""
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    _write(
        tmp_path / "astrbot" / "api" / "all.py",
        "from astrbot.api.event import MessageChain\n",
    )
    monkeypatch.setattr(
        audit,
        "show",
        lambda ref, path: "from astrbot.api.event import MessageChain, ButtonAction\n",
    )
    findings = audit.check_s8()
    assert any(
        item.level == audit.BLOCK and "ButtonAction" in item.evidence
        for item in findings
    )


def test_compare_trees_reports_missing_file(tmp_path):
    """I1/I3 must catch a file absent from the instance."""
    source, target = tmp_path / "source", tmp_path / "target"
    _write(source / "mod.py", "print('ok')\n")
    _write(target / ".keep", "")
    findings = audit.compare_trees(source, target, "I1")
    assert any(
        item.level == audit.BLOCK and "mod.py" in item.where for item in findings
    )


def test_main_json_and_exit_code(monkeypatch, capsys):
    """JSON output is parseable and a BLOCK finding makes main() return 1."""
    finding = audit.Finding("S1", audit.BLOCK, "x.py:1", "stale kvarg", "fix it")
    monkeypatch.setattr(audit, "run", lambda instance: [finding])
    assert audit.main(["--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["level"] == "BLOCK"
    assert payload[0]["check"] == "S1"
