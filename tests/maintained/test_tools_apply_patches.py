"""Tests for maintained/tools/apply_patches.py."""

import hashlib
import json
from pathlib import Path

import pytest
from tools import apply_patches, check_drift


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))


def _manifest(tmp_path: Path, files: dict[str, str]) -> Path:
    manifest = tmp_path / "installed_manifest.json"
    payload = {"files": {name: _sha(content) for name, content in files.items()}}
    manifest.write_bytes((json.dumps(payload, indent=2) + "\n").encode("utf-8"))
    return manifest


def _instance(tmp_path: Path, core_files: dict[str, str]) -> Path:
    instance = tmp_path / "instance"
    core = instance / "core"
    (core / "astrbot").mkdir(parents=True, exist_ok=True)
    for name, content in core_files.items():
        _write(core / name, content)
    return instance


def test_verify_source_accepts_matching_tree(tmp_path):
    files = {"astrbot/core/a.py": "A"}
    source = tmp_path / "source"
    _write(source / "astrbot/core/a.py", "A")
    assert (
        apply_patches.verify_source(source, {k: _sha(v) for k, v in files.items()})
        == []
    )


def test_verify_source_reports_broken_sources(tmp_path):
    expected = {"astrbot/core/a.py": _sha("A"), "astrbot/core/b.py": _sha("B")}
    source = tmp_path / "source"
    _write(source / "astrbot/core/a.py", "TAMPERED")
    assert apply_patches.verify_source(source, expected) == [
        "astrbot/core/a.py",
        "astrbot/core/b.py",
    ]


def test_build_plan_classifies_each_entry(tmp_path):
    expected = {
        "astrbot/core/same.py": _sha("SAME"),
        "astrbot/core/changed.py": _sha("NEW"),
        "astrbot/core/new.py": _sha("NEW"),
    }
    core = tmp_path / "core"
    _write(core / "astrbot/core/same.py", "SAME")
    _write(core / "astrbot/core/changed.py", "OLD")

    plan = {(c.relative, c.action) for c in apply_patches.build_plan(core, expected)}
    assert plan == {
        ("astrbot/core/same.py", apply_patches.ACTION_SKIP),
        ("astrbot/core/changed.py", apply_patches.ACTION_UPDATE),
        ("astrbot/core/new.py", apply_patches.ACTION_CREATE),
    }


def test_backup_files_records_pre_state(tmp_path):
    instance = _instance(tmp_path, {"astrbot/core/changed.py": "OLD"})
    core = instance / "core"
    change = apply_patches.Change(
        "astrbot/core/changed.py", apply_patches.ACTION_UPDATE
    )

    backup_dir, records = apply_patches.backup_files([change], core, instance)

    assert backup_dir.is_dir()
    assert records[0]["state_before"] == "present"
    assert records[0]["sha256"] == _sha("OLD")
    assert (backup_dir / "core/astrbot/core/changed.py").read_bytes() == b"OLD"


def test_backup_files_marks_absent_for_creates(tmp_path):
    instance = _instance(tmp_path, {})
    change = apply_patches.Change("astrbot/core/new.py", apply_patches.ACTION_CREATE)
    _, records = apply_patches.backup_files([change], instance / "core", instance)
    assert records[0]["state_before"] == "absent"
    assert records[0]["sha256"] is None


def test_main_dry_run_writes_nothing(tmp_path, capsys):
    files = {"astrbot/core/a.py": "NEW"}
    manifest = _manifest(tmp_path, files)
    instance = _instance(tmp_path, {"astrbot/core/a.py": "OLD"})
    source = tmp_path / "source"
    _write(source / "astrbot/core/a.py", "NEW")

    code = apply_patches.main(
        [
            "--instance",
            str(instance),
            "--manifest",
            str(manifest),
            "--source",
            str(source),
        ]
    )
    assert code == 0
    assert "DRY RUN" in capsys.readouterr().out
    assert (instance / "core/astrbot/core/a.py").read_bytes() == b"OLD"
    assert not (instance / "optimization_backups").exists()


def test_main_apply_writes_backs_up_and_verifies(tmp_path, capsys):
    files = {"astrbot/core/a.py": "NEW"}
    manifest = _manifest(tmp_path, files)
    instance = _instance(tmp_path, {"astrbot/core/a.py": "OLD"})
    source = tmp_path / "source"
    _write(source / "astrbot/core/a.py", "NEW")

    code = apply_patches.main(
        [
            "--instance",
            str(instance),
            "--manifest",
            str(manifest),
            "--source",
            str(source),
            "--apply",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert (instance / "core/astrbot/core/a.py").read_bytes() == b"NEW"
    assert "verify : 1 entries -> 1 ok" in out

    backups = list((instance / "optimization_backups").iterdir())
    assert len(backups) == 1
    assert (backups[0] / "manifest.json").is_file()
    assert (backups[0] / "RESTORE.md").is_file()
    assert (backups[0] / "core/astrbot/core/a.py").read_bytes() == b"OLD"


def test_main_reports_nothing_to_do(tmp_path, capsys):
    files = {"astrbot/core/a.py": "SAME"}
    manifest = _manifest(tmp_path, files)
    instance = _instance(tmp_path, files)
    source = tmp_path / "source"
    _write(source / "astrbot/core/a.py", "SAME")

    code = apply_patches.main(
        [
            "--instance",
            str(instance),
            "--manifest",
            str(manifest),
            "--source",
            str(source),
        ]
    )
    assert code == 0
    assert "nothing to do" in capsys.readouterr().out


def test_main_aborts_when_source_is_tampered(tmp_path, capsys):
    files = {"astrbot/core/a.py": "NEW"}
    manifest = _manifest(tmp_path, files)
    instance = _instance(tmp_path, {"astrbot/core/a.py": "OLD"})
    source = tmp_path / "source"
    _write(source / "astrbot/core/a.py", "TAMPERED")

    code = apply_patches.main(
        [
            "--instance",
            str(instance),
            "--manifest",
            str(manifest),
            "--source",
            str(source),
            "--apply",
        ]
    )
    assert code == 2
    assert "does not match the manifest" in capsys.readouterr().err
    assert (instance / "core/astrbot/core/a.py").read_bytes() == b"OLD"


def test_main_returns_two_on_bad_instance(tmp_path, capsys):
    manifest = _manifest(tmp_path, {"astrbot/core/a.py": "NEW"})
    code = apply_patches.main(
        ["--instance", str(tmp_path / "missing"), "--manifest", str(manifest)]
    )
    assert code == 2
    assert "error:" in capsys.readouterr().err


def test_apply_makes_check_drift_clean(tmp_path):
    files = {"astrbot/core/a.py": "NEW", "astrbot/api/b.py": "NEW"}
    manifest = _manifest(tmp_path, files)
    instance = _instance(tmp_path, {"astrbot/core/a.py": "OLD"})
    source = tmp_path / "source"
    for name, content in files.items():
        _write(source / name, content)

    assert (
        apply_patches.main(
            [
                "--instance",
                str(instance),
                "--manifest",
                str(manifest),
                "--source",
                str(source),
                "--apply",
            ]
        )
        == 0
    )

    expected = check_drift.load_manifest(manifest)
    assert check_drift.compare(instance / "core", expected).consistent
