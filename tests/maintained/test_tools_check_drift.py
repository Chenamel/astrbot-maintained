"""Tests for maintained/tools/check_drift.py."""

import hashlib
import json
from pathlib import Path

import pytest
from tools import check_drift


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _make_manifest(tmp_path: Path, files: dict[str, str]) -> Path:
    manifest = tmp_path / "installed_manifest.json"
    payload = {
        "proactive_must_remain_disabled": True,
        "files": {name: _sha(content) for name, content in files.items()},
    }
    manifest.write_bytes((json.dumps(payload, indent=2) + "\n").encode("utf-8"))
    return manifest


def _make_tree(root: Path, files: dict[str, str]) -> Path:
    for name, content in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8"))
    return root


def test_load_manifest_roundtrip(tmp_path):
    manifest = _make_manifest(tmp_path, {"astrbot/core/a.py": "A"})
    loaded = check_drift.load_manifest(manifest)
    assert loaded == {"astrbot/core/a.py": _sha("A")}


def test_load_manifest_rejects_missing_files_key(tmp_path):
    manifest = tmp_path / "m.json"
    manifest.write_bytes(b'{"other": 1}')
    with pytest.raises(ValueError):
        check_drift.load_manifest(manifest)


def test_load_manifest_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        check_drift.load_manifest(tmp_path / "nope.json")


def test_compare_reports_ok_mismatch_and_missing(tmp_path):
    files = {"astrbot/core/a.py": "A", "astrbot/core/b.py": "B", "astrbot/api/c.py": "C"}
    manifest = _make_manifest(tmp_path, files)
    expected = check_drift.load_manifest(manifest)

    tree = tmp_path / "tree"
    _make_tree(tree, {"astrbot/core/a.py": "A", "astrbot/core/b.py": "CHANGED"})

    report = check_drift.compare(tree, expected)
    assert report.entries["astrbot/core/a.py"] == check_drift.STATUS_OK
    assert report.entries["astrbot/core/b.py"] == check_drift.STATUS_MISMATCH
    assert report.entries["astrbot/api/c.py"] == check_drift.STATUS_MISSING
    assert report.drift == ["astrbot/core/b.py", "astrbot/api/c.py"]
    assert not report.consistent
    assert report.total == 3


def test_compare_clean_tree(tmp_path):
    files = {"astrbot/core/a.py": "A"}
    manifest = _make_manifest(tmp_path, files)
    tree = _make_tree(tmp_path / "tree", files)

    report = check_drift.compare(tree, check_drift.load_manifest(manifest))
    assert report.consistent
    assert report.counts() == {
        check_drift.STATUS_OK: 1,
        check_drift.STATUS_MISMATCH: 0,
        check_drift.STATUS_MISSING: 0,
    }


def test_report_to_dict_is_serialisable(tmp_path):
    files = {"astrbot/core/a.py": "A"}
    manifest = _make_manifest(tmp_path, files)
    tree = _make_tree(tmp_path / "tree", files)
    report = check_drift.compare(tree, check_drift.load_manifest(manifest))
    assert json.loads(json.dumps(report.to_dict()))["consistent"] is True


def test_resolve_core_accepts_instance_root(tmp_path):
    (tmp_path / "core" / "astrbot").mkdir(parents=True)
    assert check_drift.resolve_core(tmp_path) == tmp_path / "core"


def test_resolve_core_accepts_core_directory(tmp_path):
    (tmp_path / "astrbot").mkdir(parents=True)
    assert check_drift.resolve_core(tmp_path) == tmp_path


def test_resolve_core_raises_without_core(tmp_path):
    with pytest.raises(FileNotFoundError):
        check_drift.resolve_core(tmp_path)


def test_main_returns_zero_when_clean(tmp_path, capsys):
    files = {"astrbot/core/a.py": "A"}
    manifest = _make_manifest(tmp_path, files)
    core = _make_tree(tmp_path / "core", files)
    (core / "astrbot").mkdir(parents=True, exist_ok=True)

    code = check_drift.main(["--instance", str(tmp_path), "--manifest", str(manifest)])
    assert code == 0
    assert "NO DRIFT" in capsys.readouterr().out


def test_main_returns_one_on_drift(tmp_path, capsys):
    manifest = _make_manifest(tmp_path, {"astrbot/core/a.py": "A"})
    core = tmp_path / "core"
    (core / "astrbot").mkdir(parents=True)

    code = check_drift.main(["--instance", str(tmp_path), "--manifest", str(manifest)])
    assert code == 1
    assert "DRIFT DETECTED" in capsys.readouterr().out


def test_main_json_output(tmp_path, capsys):
    manifest = _make_manifest(tmp_path, {"astrbot/core/a.py": "A"})
    (tmp_path / "core" / "astrbot").mkdir(parents=True)

    code = check_drift.main(
        ["--instance", str(tmp_path), "--manifest", str(manifest), "--json"]
    )
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["instance"]["consistent"] is False


def test_main_returns_two_on_bad_instance(tmp_path, capsys):
    manifest = _make_manifest(tmp_path, {"astrbot/core/a.py": "A"})
    code = check_drift.main(["--instance", str(tmp_path), "--manifest", str(manifest)])
    assert code == 2
    assert "error:" in capsys.readouterr().err
