"""Record and verify the completion-hook ordering of the tool-loop agent runner.

The fork fires ``BaseAgentRunHooks.on_agent_done`` **before** the final reply is
emitted on the skills-like re-query path (``hook_timing_mode="enhanced"``);
``legacy`` restores the upstream ordering. T8-12 splits four oversized core
files, and the five ``_complete_with_assistant_response`` call sites must stay
faithful while that happens.

This probe replays one scripted scenario per call site, records the interleaving
of the completion hook and the emitted agent responses, and stores it as a
baseline::

    python maintained/tools/hook_timing_probe.py --dump maintained/baselines/hook_timing/<sha>.json
    python maintained/tools/hook_timing_probe.py --compare maintained/baselines/hook_timing/<sha>.json

Exit codes:
    0 -- every case matches the baseline (or the dump was written)
    1 -- a case, a timing invariant, or a structural guard failed
    2 -- usage or environment error

Comparison covers ``events``, ``summary`` and ``mode_symmetry`` only.
``repo_commit`` and ``case.call_site`` are informational: they are expected to
move when the runner is edited, which is exactly why the invariant is expressed
as a *relative* ordering instead of an absolute line number.

See ``docs/maintained/api-contract.md`` (hook timing mode) and
``tests/maintained/test_hook_timing_mode.py``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(REPO_ROOT))

from astrbot.core.agent.hooks import BaseAgentRunHooks  # noqa: E402
from astrbot.core.agent.run_context import ContextWrapper  # noqa: E402
from astrbot.core.agent.runners.tool_loop_agent_runner import (  # noqa: E402
    ToolLoopAgentRunner,
)
from astrbot.core.agent.tool import FunctionTool, ToolSet  # noqa: E402
from astrbot.core.provider.entities import LLMResponse, ProviderRequest  # noqa: E402
from astrbot.core.provider.provider import Provider  # noqa: E402

__all__ = [
    "SCHEMA_VERSION",
    "build_report",
    "structural_guard",
    "main",
]

SCHEMA_VERSION = 1
DEFAULT_BASELINE_DIR = REPO_ROOT / "maintained" / "baselines" / "hook_timing"
RUNNER_REL_PATH = "astrbot/core/agent/runners/tool_loop_agent_runner.py"

CALL_SITE_MARKER = "await self._complete_with_assistant_response("
EXPECTED_CALL_SITES = 5
EXPECTED_TIMING_SITES = {"enhanced": 1, "legacy": 1}

HOOK_EVENT_KIND = "agent_done"
IMAGE_UNAVAILABLE_TEXT = "当前看不到图片，请重新发送。"
PLAIN_REPLY_TEXT = "Here is the answer."
REQUERY_FINAL_TEXT = "The search is complete: two pushes."
TOOL_FAILURE_TEXT = "Tool run failed; nothing to report."


@dataclass(frozen=True)
class CaseSpec:
    """One probed completion-hook call site.

    Attributes:
        name: Stable case identifier used as the comparison key.
        call_site: Runner line number at the time the baseline was written
            (informational; it moves when the runner is edited).
        mode: ``hook_timing_mode`` to run the case with.
        final_text: Reply text that marks the end of the scenario.
        timing_branch: ``""`` for call sites with no ``legacy_timing`` branch,
            otherwise ``enhanced`` or ``legacy``.
        max_step: Upper bound passed to ``step_until_done``.
    """

    name: str
    call_site: int
    mode: str
    final_text: str
    timing_branch: str
    max_step: int


CASES: tuple[CaseSpec, ...] = (
    CaseSpec("image_unavailable", 984, "enhanced", IMAGE_UNAVAILABLE_TEXT, "", 4),
    CaseSpec("no_tool_call", 1100, "enhanced", PLAIN_REPLY_TEXT, "", 4),
    CaseSpec("requery_enhanced", 1142, "enhanced", REQUERY_FINAL_TEXT, "enhanced", 4),
    CaseSpec("requery_legacy", 1166, "legacy", REQUERY_FINAL_TEXT, "legacy", 4),
    CaseSpec("tool_failure_final", 1340, "enhanced", TOOL_FAILURE_TEXT, "", 8),
)

# Call sites with no legacy_timing branch must behave identically in both modes.
SYMMETRY_CASES: tuple[str, ...] = (
    "image_unavailable",
    "no_tool_call",
    "tool_failure_final",
)


def _plain_reply(text: str) -> Callable[[], LLMResponse]:
    """Return a factory for a plain assistant reply.

    Args:
        text: Completion text of the reply.

    Returns:
        A callable producing a fresh ``LLMResponse`` on every call.
    """

    def factory() -> LLMResponse:
        return LLMResponse(role="assistant", completion_text=text)

    return factory


def _tool_call() -> LLMResponse:
    """Return a fresh assistant response carrying one tool call."""
    return LLMResponse(
        role="assistant",
        completion_text="Let me check.",
        tools_call_name=["probe_tool"],
        tools_call_args=[{"query": "same"}],
        tools_call_ids=["probe_tool_call"],
    )


class _ScriptedProvider(Provider):
    """Provider stub replaying a fixed script of responses."""

    def __init__(self, script: list[Callable[[], LLMResponse]]) -> None:
        super().__init__({}, {})
        self.script = script
        self.call_count = 0

    def get_current_key(self) -> str:
        return "probe_key"

    def set_key(self, key: str) -> None:
        return None

    async def get_models(self) -> list[str]:
        return ["probe_model"]

    async def text_chat(self, **kwargs) -> LLMResponse:
        self.call_count += 1
        return self.script[min(self.call_count, len(self.script)) - 1]()

    async def text_chat_stream(self, **kwargs):
        response = await self.text_chat(**kwargs)
        response.is_chunk = True
        yield response
        response.is_chunk = False
        yield response


class _IdleToolExecutor:
    """Executor stub; the probed paths must never run a tool."""

    def execute(self, tool, run_context, **tool_args):
        raise AssertionError("the probed path must not execute tools")


class _FailingToolExecutor:
    """Executor stub whose every tool call raises the same error."""

    def execute(self, tool, run_context, **tool_args):
        raise RuntimeError("probe tool exploded")


class _RecordingHooks(BaseAgentRunHooks):
    """Agent hooks appending a marker when the completion hook fires."""

    def __init__(self, log: list[dict]) -> None:
        self.log = log
        self.done_calls = 0

    async def on_agent_begin(self, run_context) -> None:
        return None

    async def on_tool_start(self, run_context, tool, tool_args) -> None:
        return None

    async def on_tool_end(self, run_context, tool, tool_args, tool_result) -> None:
        return None

    async def on_agent_done(self, run_context, llm_response) -> None:
        self.done_calls += 1
        self.log.append({"kind": HOOK_EVENT_KIND, "text": "", "hook_done": True})


def _probe_tool() -> FunctionTool:
    """Return the single tool used by every scripted scenario."""
    return FunctionTool(
        name="probe_tool",
        description="probe tool",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        handler=AsyncMock(),
    )


def _build_case(name: str) -> tuple[_ScriptedProvider, ProviderRequest, object, str]:
    """Build the provider, request, tool executor and schema mode of a case.

    Args:
        name: Case identifier.

    Returns:
        Tuple of provider, request, tool executor and ``tool_schema_mode``.

    Raises:
        ValueError: When the case name is unknown.
    """
    if name == "image_unavailable":
        return (
            _ScriptedProvider([_plain_reply(PLAIN_REPLY_TEXT)]),
            ProviderRequest(
                prompt="look at this",
                contexts=[],
                image_input_unavailable=True,
            ),
            _IdleToolExecutor(),
            "full",
        )
    if name == "no_tool_call":
        return (
            _ScriptedProvider([_plain_reply(PLAIN_REPLY_TEXT)]),
            ProviderRequest(
                prompt="hello",
                contexts=[],
                func_tool=ToolSet(tools=[_probe_tool()]),
            ),
            _IdleToolExecutor(),
            "full",
        )
    if name in ("requery_enhanced", "requery_legacy"):
        return (
            _ScriptedProvider([_tool_call, _plain_reply(REQUERY_FINAL_TEXT)]),
            ProviderRequest(
                prompt="please look this up",
                contexts=[],
                func_tool=ToolSet(tools=[_probe_tool()]),
            ),
            _IdleToolExecutor(),
            "skills_like",
        )
    if name == "tool_failure_final":
        return (
            _ScriptedProvider(
                [
                    _tool_call,
                    _tool_call,
                    _tool_call,
                    _plain_reply(TOOL_FAILURE_TEXT),
                ],
            ),
            ProviderRequest(
                prompt="run the tool",
                contexts=[],
                func_tool=ToolSet(tools=[_probe_tool()]),
            ),
            _FailingToolExecutor(),
            "full",
        )
    raise ValueError(f"unknown probe case: {name}")


async def _execute_case(spec: CaseSpec, mode: str) -> tuple[list[dict], dict]:
    """Run one scenario and record the hook/response interleaving.

    Args:
        spec: Case definition.
        mode: ``hook_timing_mode`` to run with.

    Returns:
        Tuple of the indexed event list and the case summary.
    """
    provider, request, tool_executor, tool_schema_mode = _build_case(spec.name)
    log: list[dict] = []
    hooks = _RecordingHooks(log)
    runner = ToolLoopAgentRunner()
    await runner.reset(
        provider=provider,
        request=request,
        run_context=ContextWrapper(context=None),
        tool_executor=tool_executor,
        agent_hooks=hooks,
        streaming=False,
        tool_schema_mode=tool_schema_mode,
        hook_timing_mode=mode,
    )

    original_step = runner.step

    async def recorded_step():
        async for response in original_step():
            data = response.data
            chain = data.get("chain") if isinstance(data, dict) else None
            log.append(
                {
                    "kind": response.type,
                    "text": chain.get_plain_text() if chain is not None else "",
                    "hook_done": hooks.done_calls > 0,
                },
            )
            yield response

    runner.step = recorded_step
    async for _ in runner.step_until_done(spec.max_step):
        pass

    events = [{"i": index, **entry} for index, entry in enumerate(log)]
    summary = {
        "hook_done": hooks.done_calls > 0,
        "provider_calls": provider.call_count,
        "done": runner.done(),
        "hook_index": next(
            (e["i"] for e in events if e["kind"] == HOOK_EVENT_KIND),
            -1,
        ),
        "first_final_yield_index": next(
            (
                e["i"]
                for e in events
                if e["kind"] == "llm_result" and e["text"] == spec.final_text
            ),
            -1,
        ),
    }
    return events, summary


def _invariant_holds(spec: CaseSpec, mode: str, summary: dict) -> bool:
    """Return whether the relative hook/reply ordering matches the mode.

    Args:
        spec: Case definition.
        mode: ``hook_timing_mode`` the case ran with.
        summary: Summary produced by ``_execute_case``.

    Returns:
        True when the hook index relates to the final yield as the mode demands.
    """
    hook_index = summary["hook_index"]
    final_index = summary["first_final_yield_index"]
    if hook_index < 0 or final_index < 0:
        return False
    if spec.timing_branch == "legacy" or mode == "legacy" and spec.timing_branch:
        return hook_index > final_index
    return hook_index < final_index


def _fingerprint(events: list[dict], summary: dict) -> str:
    """Return a stable digest of one case's observable behaviour."""
    payload = json.dumps(
        {"events": events, "summary": summary},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def structural_guard(runner_path: Path) -> tuple[list[dict], list[str]]:
    """Check the completion-hook call sites without relying on line numbers.

    Args:
        runner_path: Path to ``tool_loop_agent_runner.py``.

    Returns:
        Tuple of the detected call sites and the list of guard violations.
    """
    lines = runner_path.read_text(encoding="utf-8").splitlines()
    sites: list[dict] = []
    for index, line in enumerate(lines):
        if CALL_SITE_MARKER not in line:
            continue
        branch = ""
        for back in range(1, 7):
            previous = lines[index - back].strip() if index - back >= 0 else ""
            if previous.startswith("if not legacy_timing:"):
                branch = "enhanced"
                break
            if previous.startswith("if legacy_timing:"):
                branch = "legacy"
                break
            if previous.startswith(
                ("if ", "elif ", "else:", "try:", "for ", "while ", "async for"),
            ):
                break
        sites.append({"line": index + 1, "branch": branch})

    errors: list[str] = []
    if len(sites) != EXPECTED_CALL_SITES:
        errors.append(
            f"expected {EXPECTED_CALL_SITES} call sites, found {len(sites)}",
        )
    counts = {"": 0, "enhanced": 0, "legacy": 0}
    for site in sites:
        counts[site["branch"]] = counts.get(site["branch"], 0) + 1
    if counts["enhanced"] != EXPECTED_TIMING_SITES["enhanced"]:
        errors.append(
            f"expected {EXPECTED_TIMING_SITES['enhanced']} enhanced-branch site, "
            f"found {counts['enhanced']}",
        )
    if counts["legacy"] != EXPECTED_TIMING_SITES["legacy"]:
        errors.append(
            f"expected {EXPECTED_TIMING_SITES['legacy']} legacy-branch site, "
            f"found {counts['legacy']}",
        )
    return sites, errors


def repo_commit() -> str:
    """Return the short HEAD sha, or ``unknown`` when git is unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip()


def build_report() -> dict:
    """Run every case and return the probe report.

    Returns:
        Mapping with ``schema``, ``generated_by``, ``repo_commit``, ``cases``
        and ``mode_symmetry``.
    """
    cases: list[dict] = []
    symmetry: list[dict] = []
    by_name: dict[str, dict] = {}
    for spec in CASES:
        events, summary = asyncio.run(_execute_case(spec, spec.mode))
        case = {
            "case": spec.name,
            "call_site": spec.call_site,
            "mode": spec.mode,
            "events": events,
            "summary": summary,
            "invariant_ok": _invariant_holds(spec, spec.mode, summary),
        }
        cases.append(case)
        by_name[spec.name] = case

    for name in SYMMETRY_CASES:
        spec = next(s for s in CASES if s.name == name)
        opposite = "legacy" if spec.mode == "enhanced" else "enhanced"
        events, summary = asyncio.run(_execute_case(spec, opposite))
        reference = by_name[name]
        identical = (
            events == reference["events"] and summary == reference["summary"]
        ) and _invariant_holds(spec, opposite, summary)
        symmetry.append(
            {
                "case": name,
                "call_site": spec.call_site,
                "modes": [spec.mode, opposite],
                "identical": identical,
                "fingerprint": _fingerprint(
                    reference["events"],
                    reference["summary"],
                ),
            },
        )

    return {
        "schema": SCHEMA_VERSION,
        "generated_by": "maintained/tools/hook_timing_probe.py",
        "repo_commit": repo_commit(),
        "cases": cases,
        "mode_symmetry": symmetry,
    }


def _print_report(report: dict, sites: list[dict]) -> None:
    """Print a human-readable report."""
    print(f"repo_commit {report['repo_commit']}")
    print(
        "call sites: "
        + ", ".join(f"{site['line']}({site['branch'] or 'plain'})" for site in sites),
    )
    for case in report["cases"]:
        summary = case["summary"]
        print(
            f"  {case['case']:<19} mode={case['mode']:<8} "
            f"hook_index={summary['hook_index']} "
            f"final_index={summary['first_final_yield_index']} "
            f"calls={summary['provider_calls']} "
            f"done={summary['done']} "
            f"invariant={'ok' if case['invariant_ok'] else 'FAIL'}",
        )
    for entry in report["mode_symmetry"]:
        print(
            f"  symmetry {entry['case']:<19} "
            f"{'+'.join(entry['modes'])} "
            f"{'identical' if entry['identical'] else 'DIFFERS'} "
            f"{entry['fingerprint'][:12]}",
        )


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(
        description="Record and verify the tool-loop completion-hook ordering.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dump",
        type=Path,
        help="Write the current behaviour to a baseline JSON file.",
    )
    group.add_argument(
        "--compare",
        type=Path,
        help="Compare the current behaviour against a baseline JSON file.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Silence AstrBot log output below ERROR (the runner logs tracebacks).",
    )
    args = parser.parse_args(argv)
    if args.quiet:
        logging.getLogger("astrbot").setLevel(logging.ERROR)

    runner_path = REPO_ROOT / RUNNER_REL_PATH
    if not runner_path.is_file():
        print(f"error: runner not found: {runner_path}", file=sys.stderr)
        return 2
    sites, guard_errors = structural_guard(runner_path)
    report = build_report()

    failures: list[str] = list(guard_errors)
    for case in report["cases"]:
        if not case["invariant_ok"]:
            failures.append(f"{case['case']}: timing invariant violated")
    for entry in report["mode_symmetry"]:
        if not entry["identical"]:
            failures.append(f"{entry['case']}: mode symmetry broken")

    if args.compare is not None:
        if not args.compare.is_file():
            print(f"error: baseline not found: {args.compare}", file=sys.stderr)
            return 2
        baseline = json.loads(args.compare.read_text(encoding="utf-8"))
        expected_cases = {c["case"]: c for c in baseline.get("cases", [])}
        for case in report["cases"]:
            expected = expected_cases.get(case["case"])
            if expected is None:
                failures.append(f"{case['case']}: missing from baseline")
                continue
            if case["events"] != expected.get("events"):
                failures.append(f"{case['case']}: events differ from baseline")
            if case["summary"] != expected.get("summary"):
                failures.append(f"{case['case']}: summary differs from baseline")
        expected_symmetry = {
            entry["case"]: entry for entry in baseline.get("mode_symmetry", [])
        }
        for entry in report["mode_symmetry"]:
            expected = expected_symmetry.get(entry["case"])
            if expected is None:
                failures.append(f"{entry['case']}: symmetry missing from baseline")
                continue
            if entry["identical"] != expected.get("identical"):
                failures.append(f"{entry['case']}: symmetry flag differs")
            if entry["fingerprint"] != expected.get("fingerprint"):
                failures.append(f"{entry['case']}: symmetry fingerprint differs")
        verdict = "MATCH" if not failures else "DIFFERS"
        print(f"baseline {args.compare} => {verdict}")
    else:
        target = args.dump
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        target.write_bytes(payload.encode("utf-8"))
        print(f"baseline written to {target}")

    _print_report(report, sites)
    for failure in failures:
        print(f"  FAIL {failure}")
    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover - exercised via main()
    raise SystemExit(main())
