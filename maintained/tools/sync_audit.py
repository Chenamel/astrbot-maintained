"""Deterministic audit of upstream-version coverage.

The release gate answers "can this be released?" by checking the fork's own
artifacts. This tool answers a different question: "did the fork actually
absorb everything the upstream version changed, and did the running instance
receive all of it?" It compares the two upstream baseline tags rather than the
fork's 68-entry manifest, because the manifest only lists files the fork edits.

Read-only. Pure standard library. See ``docs/maintained/upstream-sync-audit.md``.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[2]
OLD_BASE = "baseline/v4.28.2"
NEW_BASE = "baseline/v4.29.4"
LOCALES = ("zh-CN", "en-US", "ja-JP", "ru-RU")
BLOCK, WARN, INFO, SKIP = "BLOCK", "WARN", "INFO", "SKIP"


@dataclass(frozen=True)
class Finding:
    """One audit result.

    Args:
        check: Check identifier (S1..I5).
        level: BLOCK, WARN, INFO or SKIP.
        where: File path, optionally with a line number.
        evidence: What was observed.
        advice: What to do about it.
    """

    check: str
    level: str
    where: str
    evidence: str
    advice: str


def git(*args: str) -> tuple[int, str]:
    """Run git in the repository root and return (returncode, stdout)."""
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.returncode, result.stdout


def show(ref: str, path: str) -> str:
    """Return a file's contents at a git ref, or an empty string."""
    code, text = git("show", f"{ref}:{path}")
    return text if code == 0 else ""


def ref_exists(ref: str) -> bool:
    """Whether a git ref resolves locally."""
    code, _ = git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    return code == 0


def package_name(spec: str) -> str:
    """Extract a distribution name from a requirement specifier."""
    return re.split(r"[<>=!~\[;(\s]", spec.strip())[0].strip().lower().replace("_", "-")


def dependencies(text: str) -> dict[str, str]:
    """Parse ``[project].dependencies`` from pyproject text."""
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError):
        return {}
    return {
        package_name(item): item
        for item in data.get("project", {}).get("dependencies", [])
    }


@dataclass(frozen=True)
class Signature:
    """A callable's parameter surface."""

    names: frozenset[str]
    positional_max: int
    accepts_kwargs: bool


def signatures(source: str) -> dict[str, Signature]:
    """Collect top-level function and class-method signatures from Python source."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    out: dict[str, Signature] = {}

    def record(node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        args = node.args
        names = {a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)}
        has_varargs = args.vararg is not None
        out[node.name] = Signature(
            names=frozenset(names),
            positional_max=len(args.posonlyargs) + len(args.args)
            if not has_varargs
            else 10**6,
            accepts_kwargs=args.kwarg is not None,
        )

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            record(node)
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    record(child)
    return out


def changed_signatures(paths: list[str]) -> dict[str, dict[str, Signature | None]]:
    """Map module -> changed/removed callable -> new signature.

    A ``None`` signature means the callable existed in the old upstream baseline
    but is gone from the new one; calling it is then always a defect.
    """
    changed: dict[str, dict[str, Signature | None]] = {}
    for path in paths:
        if not path.endswith(".py"):
            continue
        old, new = signatures(show(OLD_BASE, path)), signatures(show(NEW_BASE, path))
        if not new and not old:
            continue
        delta: dict[str, Signature | None] = {
            name: new[name] for name in set(old) & set(new) if old[name] != new[name]
        }
        delta.update(dict.fromkeys(set(old) - set(new)))
        if delta:
            module = path[:-3].replace("/", ".")
            changed[module] = delta
    return changed


def module_of_import(file: Path, node: ast.ImportFrom) -> str | None:
    """Resolve an ImportFrom to a dotted module inside ``astrbot``."""
    if node.module and (node.module == "astrbot" or node.module.startswith("astrbot.")):
        return node.module
    if node.level:
        parts = list(file.relative_to(ROOT).with_suffix("").parts)
        base = parts[: len(parts) - node.level] if node.level <= len(parts) else []
        if node.module:
            base += node.module.split(".")
        dotted = ".".join(base)
        return dotted if dotted.startswith("astrbot") else None
    return None


def current_has_symbol(module: str, name: str) -> bool:
    """Whether the current tree still defines a symbol in a given module."""
    rel = Path(module.replace(".", "/"))
    for candidate in (ROOT / rel.with_suffix(".py"), ROOT / rel / "__init__.py"):
        if candidate.is_file():
            return name in signatures(
                candidate.read_text(encoding="utf-8", errors="replace")
            )
    return False


def check_s1(changed: dict[str, dict[str, Signature | None]]) -> list[Finding]:
    """Calls into upstream functions whose signatures changed during the bump."""
    findings: list[Finding] = []
    if not changed:
        return [Finding("S1", SKIP, "-", "no comparable signature changes", "none")]
    for file in sorted((ROOT / "astrbot").rglob("*.py")):
        if "__pycache__" in file.parts:
            continue
        try:
            tree = ast.parse(file.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        local: dict[str, str] = {}
        aliases: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = module_of_import(file, node)
                if mod:
                    for alias in node.names:
                        local[alias.asname or alias.name] = mod
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname and alias.name.startswith("astrbot"):
                        aliases[alias.asname] = alias.name
        rel = str(file.relative_to(ROOT))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            module: str | None = None
            name: str | None = None
            if isinstance(node.func, ast.Name):
                name, module = node.func.id, local.get(node.func.id)
            elif isinstance(node.func, ast.Attribute) and isinstance(
                node.func.value, ast.Name
            ):
                name, module = node.func.attr, aliases.get(node.func.value.id)
            if not module or not name:
                continue
            entry = changed.get(module, {}).get(name)
            if entry is None and name not in changed.get(module, {}):
                continue
            if entry is None:
                # The fork may deliberately keep an old upstream module (that is
                # what a fork is for). Only report when the symbol is truly gone
                # from the current tree as well.
                if current_has_symbol(module, name):
                    continue
                findings.append(
                    Finding(
                        "S1",
                        BLOCK,
                        f"{rel}:{node.lineno}",
                        f"{module}.{name}() was removed by upstream between the two baselines",
                        "Port the call to the upstream replacement.",
                    )
                )
                continue
            sig = entry
            if sig.accepts_kwargs:
                continue
            for kw in node.keywords:
                if kw.arg and kw.arg not in sig.names:
                    findings.append(
                        Finding(
                            "S1",
                            BLOCK,
                            f"{rel}:{node.lineno}",
                            f"{module}.{name}() no longer accepts '{kw.arg}'; "
                            f"current params: {', '.join(sorted(sig.names))}",
                            "Adapt the fork call site to the upstream signature.",
                        )
                    )
            positional = len(node.args)
            if positional > sig.positional_max:
                findings.append(
                    Finding(
                        "S1",
                        BLOCK,
                        f"{rel}:{node.lineno}",
                        f"{module}.{name}() passes {positional} positional args, "
                        f"upstream accepts at most {sig.positional_max}",
                        "Adapt the fork call site to the upstream signature.",
                    )
                )
    return findings or [
        Finding("S1", INFO, "-", "no stale calls into changed signatures", "none")
    ]


def check_s2() -> list[Finding]:
    """Upstream-added Python modules must exist in the current tree."""
    _, text = git(
        "diff", "--name-only", "--diff-filter=A", OLD_BASE, NEW_BASE, "--", "astrbot/"
    )
    added = [line for line in text.splitlines() if line.endswith(".py")]
    missing = [path for path in added if not (ROOT / path).is_file()]
    findings = [
        Finding(
            "S2",
            BLOCK,
            path,
            "added upstream but absent from HEAD",
            "Merge the upstream file.",
        )
        for path in missing
    ]
    findings.append(
        Finding(
            "S2",
            INFO,
            "-",
            f"{len(added)} upstream-added modules, {len(missing)} missing",
            "none",
        )
    )
    return findings


def check_s3() -> tuple[list[Finding], list[str]]:
    """New upstream dependencies must be declared in the fork's requirements."""
    old = dependencies(show(OLD_BASE, "pyproject.toml"))
    new = dependencies(show(NEW_BASE, "pyproject.toml"))
    current = dependencies((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    added = sorted(set(new) - set(old))
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8", errors="replace")
    declared = {
        package_name(line)
        for line in req.splitlines()
        if line.strip() and not line.startswith("#")
    }
    findings: list[Finding] = []
    for name in added:
        if name not in declared:
            findings.append(
                Finding(
                    "S3",
                    BLOCK,
                    "requirements.txt",
                    f"upstream added '{name}' but it is not declared",
                    "Add it; the instance venv installs from requirements.txt.",
                )
            )
        if name not in current:
            findings.append(
                Finding(
                    "S3",
                    BLOCK,
                    "pyproject.toml",
                    f"upstream added '{name}' but the fork dropped it",
                    "Keep upstream dependency constraints.",
                )
            )
    findings.append(
        Finding("S3", INFO, "-", f"{len(added)} new upstream dependencies", "none")
    )
    return findings, added


def import_exists(base: Path, spec: str) -> bool:
    """Whether a local frontend import specifier resolves to a file."""
    path = base / spec
    candidates = [
        path,
        path.with_suffix(".vue"),
        path.with_suffix(".ts"),
        path.with_suffix(".js"),
        Path(str(path) + ".ts"),
        Path(str(path) + ".js"),
        Path(str(path) + ".vue"),
        path / "index.ts",
        path / "index.js",
        path / "index.vue",
    ]
    return any(candidate.is_file() for candidate in candidates)


def check_s4() -> list[Finding]:
    """Frontend local imports must resolve; dangling ones break the build."""
    src = ROOT / "dashboard" / "src"
    # Only relative specifiers and the '@/src' alias are local. Bare package
    # names (@lucide/vue, @hey-api/client-axios) are resolved by the bundler.
    pattern = re.compile(
        r"""(?:from|import\s*\(?)\s*['"](@/[^'"\s]+|\.{1,2}/[^'"\s]+)['"]"""
    )
    findings: list[Finding] = []
    for file in sorted(src.rglob("*")):
        if file.suffix not in (".vue", ".ts", ".js") or "node_modules" in file.parts:
            continue
        text = file.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), 1):
            for spec in pattern.findall(line):
                spec = spec.split("?", 1)[0].split("#", 1)[0]
                base = src if spec.startswith("@/") else file.parent
                resolved = spec[2:] if spec.startswith("@/") else spec
                if import_exists(base, resolved):
                    continue
                deprecated = "DEPRECATED" in file.name
                findings.append(
                    Finding(
                        "S4",
                        INFO if deprecated else BLOCK,
                        f"{file.relative_to(ROOT)}:{line_no}",
                        f"unresolved local import '{spec}'"
                        + (
                            " (dead file, not in the build graph)" if deprecated else ""
                        ),
                        "Remove the import or restore the module.",
                    )
                )
    return findings or [
        Finding("S4", INFO, "-", "all local frontend imports resolve", "none")
    ]


def check_s5() -> list[Finding]:
    """Every per-locale feature bundle must be imported and mounted."""
    findings: list[Finding] = []
    for locale in LOCALES:
        base = ROOT / "dashboard" / "src" / "i18n" / "locales" / locale
        index = base / "index.ts"
        if not index.is_file():
            findings.append(
                Finding(
                    "S5",
                    BLOCK,
                    str(index.relative_to(ROOT)),
                    "missing index.ts",
                    "Restore it.",
                )
            )
            continue
        text = index.read_text(encoding="utf-8")
        imported = {
            match.group(1): match.group(2)
            for match in re.finditer(
                r"import\s+(\w+)\s+from\s+'\./(features/[^']+\.json)'", text
            )
        }
        on_disk = {
            f"features/{path.relative_to(base / 'features').as_posix()}"
            for path in (base / "features").rglob("*.json")
        }
        names = set(imported.values())
        for path in sorted(on_disk - names):
            findings.append(
                Finding(
                    "S5",
                    BLOCK,
                    str(index.relative_to(ROOT)),
                    f"{locale}: {path} exists but is never imported",
                    "Register the namespace in index.ts.",
                )
            )
        for name in imported:
            if len(re.findall(rf"\b{re.escape(name)}\b", text)) < 2:
                findings.append(
                    Finding(
                        "S5",
                        BLOCK,
                        str(index.relative_to(ROOT)),
                        f"{locale}: '{name}' imported but not mounted",
                        "Add it to the exported messages object.",
                    )
                )
    return findings or [
        Finding("S5", INFO, "-", "all locale bundles registered and mounted", "none")
    ]


def version_string() -> str:
    """Read ``__version__`` from the package without importing it."""
    text = (ROOT / "astrbot" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.M)
    return match.group(1) if match else ""


def check_s6() -> list[Finding]:
    """Bundled dashboard stamp and fork-specific strings."""
    dist = ROOT / "dashboard" / "dist"
    stamp = dist / "assets" / "version"
    if not stamp.is_file():
        return [
            Finding(
                "S6",
                SKIP,
                str(stamp.relative_to(ROOT)),
                "no local build artifact (normal in CI)",
                "build locally before release",
            )
        ]
    expected = f"v{version_string()}"
    actual = stamp.read_text(encoding="utf-8").strip()
    findings: list[Finding] = []
    if actual != expected:
        findings.append(
            Finding(
                "S6",
                BLOCK,
                str(stamp.relative_to(ROOT)),
                f"stamp {actual} != {expected}",
                "Rebuild and stamp the dashboard.",
            )
        )
    bundle = (
        ROOT
        / "dashboard"
        / "src"
        / "i18n"
        / "locales"
        / "zh-CN"
        / "features"
        / "calls.json"
    )
    if bundle.is_file():
        values = json.loads(bundle.read_text(encoding="utf-8"))

        def strings(obj: object) -> list[str]:
            if isinstance(obj, dict):
                return [s for v in obj.values() for s in strings(v)]
            return [obj] if isinstance(obj, str) else []

        probe = [s for s in strings(values) if len(s) >= 2][:8]
        blobs = b"\n".join(p.read_bytes() for p in (dist / "assets").glob("*.js"))
        missing = [s for s in probe if s.encode("utf-8") not in blobs]
        if missing:
            findings.append(
                Finding(
                    "S6",
                    BLOCK,
                    str(dist.relative_to(ROOT)),
                    f"fork calls.json strings missing from build: {missing[:3]}",
                    "Rebuild the dashboard (S5 may have been fixed after the last build).",
                )
            )
    return findings or [
        Finding("S6", INFO, "-", f"stamp {actual}, fork strings present", "none")
    ]


def check_s7() -> list[Finding]:
    """Python imports inside ``astrbot`` must resolve to a real module.

    Upstream deletions that the fork still imports crash the instance before the
    log system starts, which is exactly why a green ``check_drift`` is not proof
    that an instance can boot. Optional imports guarded by ``try`` are skipped.
    """
    findings: list[Finding] = []
    for file in sorted((ROOT / "astrbot").rglob("*.py")):
        if "__pycache__" in file.parts:
            continue
        try:
            tree = ast.parse(file.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        guarded = {
            line
            for node in ast.walk(tree)
            if isinstance(node, ast.Try)
            for child in (*node.body, *node.handlers)
            for line in range(
                getattr(child, "lineno", 0), getattr(child, "end_lineno", 0) + 1
            )
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.lineno in guarded:
                continue
            module = module_of_import(file, node)
            if not module:
                continue
            rel = Path(module.replace(".", "/"))
            if (ROOT / rel.with_suffix(".py")).is_file() or (
                ROOT / rel / "__init__.py"
            ).is_file():
                continue
            # ``from pkg import submodule`` is valid when the submodule exists.
            if any((ROOT / rel / f"{alias.name}.py").is_file() for alias in node.names):
                continue
            findings.append(
                Finding(
                    "S7",
                    BLOCK,
                    f"{file.relative_to(ROOT)}:{node.lineno}",
                    f"import from missing module '{module}'",
                    "Remove the stale import or restore the module.",
                )
            )
    return findings or [
        Finding("S7", INFO, "-", "all astrbot-local imports resolve", "none")
    ]


def exported_names(source: str) -> set[str]:
    """Public names re-exported by an ``astrbot/api`` module."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            out.update(
                alias.asname or alias.name for alias in node.names if alias.name != "*"
            )
        elif isinstance(node, ast.Assign) and isinstance(
            node.value, (ast.List, ast.Tuple)
        ):
            if any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
                out.update(
                    item.value
                    for item in node.value.elts
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                )
    return out


def check_s8() -> list[Finding]:
    """Plugin compatibility: no upstream ``astrbot/api`` export may disappear."""
    path = "astrbot/api/all.py"
    current = ROOT / path
    if not current.is_file():
        return [
            Finding(
                "S8",
                BLOCK,
                path,
                "API export module missing",
                "Restore astrbot/api/all.py.",
            )
        ]
    now = exported_names(current.read_text(encoding="utf-8"))
    findings: list[Finding] = []
    for ref in (OLD_BASE, NEW_BASE):
        upstream = exported_names(show(ref, path))
        missing = sorted(upstream - now)
        if missing:
            findings.append(
                Finding(
                    "S8",
                    BLOCK,
                    path,
                    f"{len(missing)} exports present at {ref} are gone: {missing[:8]}",
                    "Restore the exports; upstream plugins import these names.",
                )
            )
    return findings or [
        Finding("S8", INFO, path, f"{len(now)} API exports, none removed", "none")
    ]


def compare_trees(
    source: Path, target: Path, label: str, exclude: tuple[str, ...] = ()
) -> list[Finding]:
    """Byte-compare every file under source against target.

    Args:
        source: Repository-side tree.
        target: Instance-side tree.
        label: Check identifier for the findings.
        exclude: Relative path prefixes to skip (e.g. bundled build output).
    """
    if not target.is_dir():
        return [
            Finding(
                label,
                SKIP,
                str(target),
                "target directory absent",
                "deploy before auditing",
            )
        ]
    findings: list[Finding] = []
    missing, different = [], []
    for path in sorted(source.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        rel = path.relative_to(source)
        if any(rel.as_posix().startswith(prefix) for prefix in exclude):
            continue
        dest = target / rel
        if not dest.is_file():
            missing.append(str(rel))
        elif dest.read_bytes() != path.read_bytes():
            different.append(str(rel))
    for rel in missing[:10]:
        findings.append(
            Finding(
                label,
                BLOCK,
                f"{target.name}/{rel}",
                "missing in instance",
                "Run apply_patches / redeploy.",
            )
        )
    for rel in different[:10]:
        findings.append(
            Finding(
                label,
                BLOCK,
                f"{target.name}/{rel}",
                "differs from repository",
                "Sync the file.",
            )
        )
    if len(missing) > 10 or len(different) > 10:
        findings.append(
            Finding(
                label,
                BLOCK,
                str(target),
                f"... {len(missing)} missing, {len(different)} differing in total",
                "See the counts above; fix all of them.",
            )
        )
    if not findings:
        findings.append(
            Finding(label, INFO, str(target), "all files identical", "none")
        )
    return findings


def check_instance(instance: Path, added: list[str]) -> list[Finding]:
    """Instance-side checks: full core, venv, deployed panel, stamp, config keys."""
    core = instance / "core"
    # The bundled dashboard dist is a local build artifact; the instance serves
    # its panel from data/dist_maintained (checked by I3), so it is not deployed
    # under core/astrbot. Excluding it keeps I1 free of false positives.
    findings = compare_trees(
        ROOT / "astrbot", core / "astrbot", "I1", exclude=("dashboard/dist",)
    )

    venv = core.parent / "venv" / "Scripts" / "python.exe"
    if not venv.is_file():
        venv = core.parent / "venv" / "bin" / "python"
    if venv.is_file():
        import_names = {
            "opentelemetry-api": "opentelemetry.trace",
            "opentelemetry-sdk": "opentelemetry.sdk.resources",
        }
        for name in added:
            module = import_names.get(name, name.replace("-", "_"))
            result = subprocess.run(
                [str(venv), "-c", f"import {module}"],
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
            if result.returncode != 0:
                findings.append(
                    Finding(
                        "I2",
                        BLOCK,
                        str(venv),
                        f"'{name}' not importable in the instance venv",
                        "Install requirements.txt into the instance venv.",
                    )
                )
        findings.append(
            Finding(
                "I2", INFO, str(venv), f"checked {len(added)} new dependencies", "none"
            )
        )
    else:
        findings.append(
            Finding(
                "I2",
                SKIP,
                str(venv),
                "instance venv interpreter not found",
                "check the instance layout",
            )
        )

    findings += compare_trees(
        ROOT / "dashboard" / "dist", core / "data" / "dist_maintained", "I3"
    )

    stamp = core / "data" / "maintained_build.json"
    if stamp.is_file():
        data = json.loads(stamp.read_text(encoding="utf-8"))
        _, head = git("rev-parse", "HEAD")
        if data.get("commit", "")[:8] != head.strip()[:8]:
            findings.append(
                Finding(
                    "I4",
                    WARN,
                    str(stamp.relative_to(instance)),
                    f"commit {data.get('commit', '')[:8]} != HEAD {head.strip()[:8]}",
                    "Run apply_patches --apply.",
                )
            )
        else:
            findings.append(
                Finding(
                    "I4", INFO, "maintained_build.json", "stamp matches HEAD", "none"
                )
            )
    else:
        findings.append(
            Finding(
                "I4", SKIP, str(stamp), "no build stamp", "run apply_patches --apply"
            )
        )

    def default_config_keys(ref: str) -> set[str]:
        """Top-level keys of DEFAULT_CONFIG; nested schema keys are not config keys."""
        try:
            tree = ast.parse(show(ref, "astrbot/core/config/default.py"))
        except SyntaxError:
            return set()
        for node in tree.body:
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Dict)
                and any(
                    isinstance(t, ast.Name) and t.id == "DEFAULT_CONFIG"
                    for t in node.targets
                )
            ):
                return {
                    key.value
                    for key in node.value.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                }
        return set()

    added_keys = sorted(default_config_keys(NEW_BASE) - default_config_keys(OLD_BASE))
    cfg = core / "data" / "cmd_config.json"
    if cfg.is_file() and added_keys:
        cfg_text = cfg.read_bytes().decode("utf-8-sig")
        absent = [key for key in added_keys if f'"{key}"' not in cfg_text]
        if absent:
            findings.append(
                Finding(
                    "I5",
                    WARN,
                    str(cfg.relative_to(instance)),
                    f"upstream config keys absent: {absent[:8]}",
                    "Confirm they are optional; otherwise add defaults.",
                )
            )
        else:
            findings.append(
                Finding(
                    "I5",
                    INFO,
                    "cmd_config.json",
                    f"all {len(added_keys)} new keys present",
                    "none",
                )
            )
    else:
        findings.append(
            Finding(
                "I5",
                SKIP,
                str(cfg),
                "config not readable or no new keys",
                "check the instance layout",
            )
        )
    return findings


def run(instance: Path | None) -> list[Finding]:
    """Execute every check and return findings in a stable order."""
    findings: list[Finding] = []
    if not (ref_exists(OLD_BASE) and ref_exists(NEW_BASE)):
        return [
            Finding(
                "S*",
                SKIP,
                "-",
                f"missing {OLD_BASE} or {NEW_BASE}",
                "fetch the baseline tags: git fetch --tags",
            )
        ]
    _, changed_paths = git("diff", "--name-only", OLD_BASE, NEW_BASE, "--", "astrbot/")
    findings += check_s1(changed_signatures(changed_paths.splitlines()))
    findings += check_s2()
    s3, added = check_s3()
    findings += s3
    findings += check_s4()
    findings += check_s5()
    findings += check_s6()
    findings += check_s7()
    findings += check_s8()
    if instance:
        findings += check_instance(instance, added)
    else:
        findings.append(
            Finding(
                "I*",
                SKIP,
                "--instance",
                "no instance supplied",
                "pass --instance for I1..I5",
            )
        )
    return findings


def main(argv: list[str] | None = None) -> int:
    """Print the audit report. Exit 1 when any BLOCK finding exists."""
    parser = argparse.ArgumentParser(description="Audit upstream-version coverage.")
    parser.add_argument(
        "--instance", type=Path, default=None, help="Live instance root."
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit JSON instead of text."
    )
    args = parser.parse_args(argv)

    findings = run(args.instance)
    if args.json:
        print(
            json.dumps(
                [asdict(item) for item in findings], ensure_ascii=False, indent=2
            )
        )
    else:
        print(f"upstream sync audit | {OLD_BASE} -> {NEW_BASE} | HEAD ", end="")
        _, head = git("rev-parse", "--short", "HEAD")
        print(head.strip())
        for item in findings:
            print(f"  [{item.level:5}] {item.check:3} {item.where}")
            print(f"           {item.evidence}")
            if item.advice != "none":
                print(f"           -> {item.advice}")
        counts = {
            level: sum(1 for item in findings if item.level == level)
            for level in (BLOCK, WARN, INFO, SKIP)
        }
        print("  " + "  ".join(f"{key}={value}" for key, value in counts.items()))
        print("AUDIT BLOCKED" if counts[BLOCK] else "AUDIT CLEAN")
    return 1 if any(item.level == BLOCK for item in findings) else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
