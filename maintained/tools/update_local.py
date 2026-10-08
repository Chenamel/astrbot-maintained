"""Stage a three-way upstream merge, verify it, and package without deployment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE_SUFFIXES = {
    ".py",
    ".json",
    ".yaml",
    ".yml",
    ".md",
    ".txt",
    ".toml",
    ".vue",
    ".ts",
    ".js",
    ".css",
    ".scss",
    ".html",
    ".svg",
}
EXCLUDED = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    ".venv",
    "logs",
    "plugin_data",
}
DETERMINISTIC_TESTS = [
    "tests/test_direct_turn_delivery_guards.py",
    "data/optimization_tracking/tests/test_direct_turns.py",
    "tests/test_local_maintenance.py",
    "tests/unit/test_astr_main_agent.py",
    "tests/test_image_unavailable_delivery.py",
    "tests/test_process_stage_images.py",
    "data/optimization_tracking/tests/test_code_delivery_pipeline.py",
    "data/optimization_tracking/tests/test_core_code_delivery.py",
    "data/optimization_tracking/tests/test_lightweight_proactive_core.py",
    "data/optimization_tracking/tests/test_repeated_tool_failures.py",
    "data/optimization_tracking/tests/test_runner_unavailable_images.py",
    "data/plugins/astrbot_plugin_astrbot_enhance_mode/tests",
    "data/plugins/astrbot_plugin_content_safety_guard/tests",
    "maintenance_tools/tests",
]


def source_files(root: Path, project: str) -> dict[str, Path]:
    """Select source files without runtime secrets, media, or databases.

    Args:
        root: Source tree to inspect.
        project: Core or plugin bundle key.

    Returns:
        Safe relative source paths mapped to files.
    """
    result = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if (
            not path.is_file()
            or path.is_symlink()
            or any(p in EXCLUDED for p in relative.parts)
        ):
            continue
        if path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        if project == "core" and not (
            relative.parts[0] == "astrbot"
            or relative.parts[:2] == ("dashboard", "src")
            or str(relative) in {"main.py", "pyproject.toml"}
        ):
            continue
        if project != "core" and relative.parts[0] in {"data", "config"}:
            continue
        result[relative.as_posix()] = path
    return result


def check_installation(instance: Path) -> list[str]:
    """Compare protected installed sources and proactive state with the receipt.

    Args:
        instance: AstrBot core directory.

    Returns:
        Changed or missing relative files and state failures.
    """
    receipt = json.loads((REPO / "installed_manifest.json").read_text(encoding="utf-8"))
    errors = []
    for relative, expected in receipt["files"].items():
        target = instance / relative
        if (
            not target.is_file()
            or hashlib.sha256(target.read_bytes()).hexdigest() != expected
        ):
            errors.append(relative)
    config = instance / "data/config/astrbot_plugin_astrbot_enhance_mode_config.json"
    raw = json.loads(config.read_text(encoding="utf-8-sig"))
    if raw["active_reply"]["enable"] is not False:
        errors.append("proactive must remain disabled until explicit user enablement")
    return errors


def main() -> None:
    """Validate installation or create an isolated reviewed upstream candidate."""
    parser = argparse.ArgumentParser()
    parser.add_argument("project", choices=["core", "enhance", "safety"])
    parser.add_argument("--instance", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--ref")
    args = parser.parse_args()
    instance = args.instance.resolve()
    if args.check:
        errors = check_installation(instance)
        print(
            json.dumps(
                {"compatible_hashes": not errors, "mismatches": errors},
                ensure_ascii=False,
            )
        )
        raise SystemExit(bool(errors))
    if args.project == "core" and not args.ref:
        parser.error("Core updates require an explicit --ref.")
    state = json.loads((REPO / "sources.json").read_text(encoding="utf-8"))
    project = args.project
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = REPO / "candidates" / f"{project}_{stamp}"
    candidate.mkdir(parents=True, exist_ok=False)
    upstream = candidate / "upstream"
    command = ["git", "clone", "--depth", "1"]
    if args.ref:
        command += ["--branch", args.ref]
    subprocess.run(
        command + [state[project]["url"], str(upstream)], check=True, timeout=300
    )
    revision = subprocess.check_output(
        ["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True
    ).strip()
    base_files = source_files(REPO / "baseline_source" / project, project)
    local_files = source_files(REPO / "maintained_source" / project, project)
    new_files = source_files(upstream, project)
    merged = candidate / "merged"
    merged.mkdir()
    conflicts = []
    for relative in sorted(base_files.keys() | local_files.keys() | new_files.keys()):
        base = base_files.get(relative)
        local = local_files.get(relative)
        new = new_files.get(relative)
        base_bytes = base.read_bytes() if base else None
        local_bytes = local.read_bytes() if local else None
        new_bytes = new.read_bytes() if new else None
        base_bytes = (
            base_bytes.replace(b"\r\n", b"\n") if base_bytes is not None else None
        )
        local_bytes = (
            local_bytes.replace(b"\r\n", b"\n") if local_bytes is not None else None
        )
        new_bytes = new_bytes.replace(b"\r\n", b"\n") if new_bytes is not None else None
        target = merged / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if local_bytes == base_bytes:
            if new is not None:
                shutil.copy2(new, target)
        elif new_bytes == base_bytes or local_bytes == new_bytes:
            if local is not None:
                shutil.copy2(local, target)
        elif base is not None and local is not None and new is not None:
            shutil.copy2(local, target)
            run = subprocess.run(
                ["git", "merge-file", str(target), str(base), str(new)],
                capture_output=True,
            )
            if run.returncode:
                conflicts.append(relative)
        else:
            conflicts.append(relative)
    receipt = {
        "project": project,
        "upstream_revision": revision,
        "conflicts": conflicts,
        "deployed": False,
        "qq_sends": 0,
    }
    if conflicts:
        (candidate / "result.json").write_text(json.dumps(receipt, indent=2))
        print(
            "Merge conflicts: review candidate/result.json; no tests or deployment attempted."
        )
        raise SystemExit(2)
    # Build a secret-free, temporary runtime; never test by replacing live files.
    with tempfile.TemporaryDirectory(prefix="astrbot-maintenance-") as temporary:
        stage = Path(temporary)
        shutil.copytree(REPO / "baseline_source/core", stage, dirs_exist_ok=True)
        shutil.copytree(REPO / "maintained_source/core", stage, dirs_exist_ok=True)
        for bundle, name in (
            ("enhance", "astrbot_plugin_astrbot_enhance_mode"),
            ("safety", "astrbot_plugin_content_safety_guard"),
        ):
            shutil.copytree(
                REPO / "maintained_source" / bundle,
                stage / "data/plugins" / name,
                dirs_exist_ok=True,
            )
        destination = (
            stage
            if project == "core"
            else stage / "data/plugins" / state[project]["plugin_name"]
        )
        # Replace source tree in staging to respect upstream deletions.
        if project != "core":
            shutil.rmtree(destination)
        shutil.copytree(merged, destination, dirs_exist_ok=True)
        if project == "core":
            for relative in local_files.keys() - source_files(merged, project).keys():
                (destination / relative).unlink(missing_ok=True)
        shutil.copytree(REPO / "tests", stage / "tests", dirs_exist_ok=True)
        shutil.copytree(
            REPO / "replay", stage / "data/optimization_tracking", dirs_exist_ok=True
        )
        shutil.copytree(
            REPO / "tools",
            stage / "maintenance_tools",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
        )
        dependencies = instance / "data/optimization_tracking/test_dependencies"
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join([str(dependencies), str(stage)])
        environment["ASTRBOT_TEST_MODE"] = "true"
        environment["PYTHONIOENCODING"] = "utf-8"
        python = instance.parent / "venv/Scripts/python.exe"
        changed_python = [
            str(destination / relative)
            for relative, path in source_files(merged, project).items()
            if path.suffix == ".py"
            and "tests" not in Path(relative).parts
            and (
                relative not in new_files
                or path.read_bytes().replace(b"\r\n", b"\n")
                != new_files[relative].read_bytes().replace(b"\r\n", b"\n")
            )
        ]
        checks = [
            [
                str(python),
                "-m",
                "pytest",
                "-q",
                *DETERMINISTIC_TESTS,
            ],
            [str(python), "-m", "ruff", "check", *changed_python],
            [str(python), "-m", "compileall", "-q", str(destination)],
        ]
        outputs = []
        for command in checks:
            run = subprocess.run(
                command,
                cwd=stage,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=300,
            )
            outputs.append(
                {
                    "command": command[1:3],
                    "code": run.returncode,
                    "output": run.stdout + run.stderr,
                }
            )
            if run.returncode:
                break
        receipt["checks"] = outputs
        receipt["passed"] = all(row["code"] == 0 for row in outputs)
    (candidate / "result.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if not receipt["passed"]:
        print("Replay/static checks failed; no deployable package created.")
        raise SystemExit(3)
    hashes = {
        r: hashlib.sha256(p.read_bytes()).hexdigest()
        for r, p in source_files(merged, project).items()
    }
    (candidate / "hashes.json").write_text(json.dumps(hashes, indent=2))
    package = candidate / "reviewed_sources.zip"
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative, path in source_files(merged, project).items():
            archive.write(path, f"{project}/{relative}")
        archive.write(candidate / "result.json", "result.json")
        archive.write(candidate / "hashes.json", "hashes.json")
    print(
        f"Reviewable package: {package}. No automatic deployment; keep proactive disabled."
    )


if __name__ == "__main__":
    main()
