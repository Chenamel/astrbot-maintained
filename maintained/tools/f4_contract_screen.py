#!/usr/bin/env python3
"""Screen upstream contract changes across five frozen domains.

Read-only: every file comes from git show on a ref, so the worktree is
never touched. The baseline tag is resolved at run time from baseline/*.
"""

import argparse
import ast
import json
import subprocess
from pathlib import Path

FROZEN_CORE_SYMBOLS = [
    ("astrbot/core/agent/message.py", "TextPart"),
    ("astrbot/core/agent/message.py", "ImageURLPart"),
    ("astrbot/core/provider/provider.py", "EmbeddingProvider"),
    ("astrbot/core/utils/astrbot_path.py", "get_astrbot_data_path"),
    ("astrbot/core/utils/io.py", "download_image_by_url"),
    ("astrbot/core/utils/quoted_message_parser.py", "extract_quoted_message_images"),
]

API_FILES = [
    "astrbot/api/__init__.py",
    "astrbot/api/all.py",
    "astrbot/api/message_components.py",
    "astrbot/api/web.py",
    "astrbot/api/event/__init__.py",
    "astrbot/api/star/__init__.py",
    "astrbot/api/provider/__init__.py",
    "astrbot/api/util/__init__.py",
    "astrbot/api/platform/__init__.py",
]


def git_read_file(repo: Path, ref: str, rel_path: str) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(repo), "show", f"{ref}:{rel_path}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.stdout if proc.returncode == 0 else None


def extract_signatures(src: str | None) -> dict[str, dict]:
    if not src:
        return {}
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return {}
    sigs = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            pos_args = [a.arg for a in node.args.posonlyargs + node.args.args]
            kw_args = [a.arg for a in node.args.kwonlyargs]
            sigs[node.name] = {
                "kind": "function",
                "pos_args": pos_args,
                "kw_args": kw_args,
                "has_vararg": node.args.vararg is not None,
                "has_kwarg": node.args.kwarg is not None,
                "num_defaults": len(node.args.defaults),
            }
        elif isinstance(node, ast.ClassDef):
            methods = {}
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods[item.name] = [a.arg for a in item.args.args]
            sigs[node.name] = {"kind": "class", "methods": methods}
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    sigs[t.id] = {"kind": "symbol"}
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                exported = alias.asname or alias.name
                sigs[exported] = {"kind": "reexport"}
    return sigs


def diff_domain_api(repo: Path, base: str, target: str) -> list[dict]:
    issues = []
    for rel in API_FILES:
        b_sigs = extract_signatures(git_read_file(repo, base, rel))
        t_sigs = extract_signatures(git_read_file(repo, target, rel))
        for sym, b_meta in b_sigs.items():
            if sym.startswith("_") and sym != "__all__":
                continue
            if sym not in t_sigs:
                issues.append(
                    {
                        "domain": "1_api_surface",
                        "file": rel,
                        "symbol": sym,
                        "issue": "removed_in_target",
                    }
                )
                continue
            t_meta = t_sigs[sym]
            if b_meta.get("kind") == "function" and t_meta.get("kind") == "function":
                if b_meta["pos_args"] != t_meta["pos_args"][: len(b_meta["pos_args"])]:
                    issues.append(
                        {
                            "domain": "1_api_surface",
                            "file": rel,
                            "symbol": sym,
                            "issue": "positional_args_changed",
                            "base": b_meta["pos_args"],
                            "target": t_meta["pos_args"],
                        }
                    )
    return issues


def diff_domain_web_bridge(repo: Path, base: str, target: str) -> list[dict]:
    issues = []
    b_web = git_read_file(repo, base, "astrbot/api/web.py") or ""
    t_web = git_read_file(repo, target, "astrbot/api/web.py") or ""
    if (
        "astrbot_plugin_web_request" in b_web
        and "astrbot_plugin_web_request" not in t_web
    ):
        issues.append(
            {
                "domain": "2_plugin_web_bridge",
                "file": "astrbot/api/web.py",
                "issue": "astrbot_plugin_web_request_removed",
            }
        )
    return issues


def diff_domain_hook_timing(repo: Path, base: str, target: str) -> list[dict]:
    issues = []
    rel = "astrbot/core/agent/runners/tool_loop_agent_runner.py"
    t_src = git_read_file(repo, target, rel)
    if t_src is None:
        issues.append(
            {
                "domain": "3_hook_timing",
                "file": rel,
                "issue": "runner_file_missing_or_moved",
            }
        )
        return issues
    call_count = t_src.count("_complete_with_assistant_response(")
    if call_count == 0:
        issues.append(
            {
                "domain": "3_hook_timing",
                "file": rel,
                "issue": "_complete_with_assistant_response_refactored",
            }
        )
    return issues


def diff_domain_media_and_frozen(repo: Path, base: str, target: str) -> list[dict]:
    issues = []
    for rel, sym in FROZEN_CORE_SYMBOLS:
        b_sigs = extract_signatures(git_read_file(repo, base, rel))
        t_sigs = extract_signatures(git_read_file(repo, target, rel))
        if sym not in t_sigs:
            issues.append(
                {
                    "domain": "4_media_and_frozen_core",
                    "file": rel,
                    "symbol": sym,
                    "issue": "frozen_symbol_missing",
                }
            )
        elif b_sigs.get(sym) != t_sigs.get(sym):
            issues.append(
                {
                    "domain": "4_media_and_frozen_core",
                    "file": rel,
                    "symbol": sym,
                    "issue": "frozen_symbol_signature_changed",
                    "base": b_sigs.get(sym),
                    "target": t_sigs.get(sym),
                }
            )
    return issues


def diff_domain_permissions(repo: Path, base: str, target: str) -> list[dict]:
    issues = []
    util_rel = "astrbot/core/tools/computer_tools/util.py"
    init_rel = "astrbot/core/tools/computer_tools/__init__.py"
    for rel in (util_rel, init_rel):
        t_sigs = extract_signatures(git_read_file(repo, target, rel))
        if "check_admin_permission" not in t_sigs:
            issues.append(
                {
                    "domain": "5_tool_permission_entry",
                    "file": rel,
                    "symbol": "check_admin_permission",
                    "issue": "permission_entry_missing",
                }
            )
    return issues


def latest_baseline(repo: Path) -> str:
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "for-each-ref",
            "--sort=-version:refname",
            "--format=%(refname:short)",
            "refs/tags/baseline/",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    tags = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if not tags:
        raise SystemExit("no baseline/* tags found in this repository")
    return tags[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".", help="Git repository path")
    parser.add_argument(
        "--base", default=None, help="Baseline tag; defaults to newest baseline/*"
    )
    parser.add_argument(
        "--target", default="HEAD", help="Ref to screen against the baseline"
    )
    args = parser.parse_args()

    repo = Path(args.repo)
    base = args.base or latest_baseline(repo)
    issues = (
        diff_domain_api(repo, base, args.target)
        + diff_domain_web_bridge(repo, base, args.target)
        + diff_domain_hook_timing(repo, base, args.target)
        + diff_domain_media_and_frozen(repo, base, args.target)
        + diff_domain_permissions(repo, base, args.target)
    )
    report = {
        "base_ref": base,
        "target_ref": args.target,
        "breaking_changes_count": len(issues),
        "issues": issues,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
