"""Tests for maintained/tools/hook_timing_probe.py."""

import json
from pathlib import Path

from tools import hook_timing_probe

RUNNER_PATH = (
    Path(__file__).resolve().parents[2]
    / "astrbot"
    / "core"
    / "agent"
    / "runners"
    / "tool_loop_agent_runner.py"
)


def _source_with_sites(branches: list[str]) -> str:
    lines = ["class R:", "    async def _step(self):"]
    for branch in branches:
        if branch:
            lines.append(f"        if {branch}:")
            lines.append("            await self._complete_with_assistant_response(x)")
        else:
            lines.append("        if llm_resp.tools_call_name:")
            lines.append("            await self._complete_with_assistant_response(x)")
    return "\n".join(lines) + "\n"


def test_structural_guard_accepts_the_current_runner():
    sites, errors = hook_timing_probe.structural_guard(RUNNER_PATH)

    assert errors == []
    assert len(sites) == hook_timing_probe.EXPECTED_CALL_SITES
    assert [site["branch"] for site in sites].count("enhanced") == 1
    assert [site["branch"] for site in sites].count("legacy") == 1
    assert [site["branch"] for site in sites].count("") == 3


def test_structural_guard_reports_a_dropped_branch(tmp_path):
    source = _source_with_sites(["", "", "not legacy_timing", "legacy_timing"])
    target = tmp_path / "runner.py"
    target.write_bytes(source.encode("utf-8"))

    sites, errors = hook_timing_probe.structural_guard(target)

    assert len(sites) == 4
    assert any("expected 5 call sites" in error for error in errors)


def test_structural_guard_reports_a_missing_legacy_branch(tmp_path):
    source = _source_with_sites(["", "", "", "not legacy_timing"])
    target = tmp_path / "runner.py"
    target.write_bytes(source.encode("utf-8"))

    _, errors = hook_timing_probe.structural_guard(target)

    assert any("legacy-branch site" in error for error in errors)


def test_dump_then_compare_roundtrip(tmp_path):
    baseline = tmp_path / "baseline.json"

    assert hook_timing_probe.main(["--quiet", "--dump", str(baseline)]) == 0
    assert hook_timing_probe.main(["--quiet", "--compare", str(baseline)]) == 0

    report = json.loads(baseline.read_text(encoding="utf-8"))
    assert report["schema"] == hook_timing_probe.SCHEMA_VERSION
    assert [case["case"] for case in report["cases"]] == [
        spec.name for spec in hook_timing_probe.CASES
    ]
    assert all(case["invariant_ok"] for case in report["cases"])
    assert all(entry["identical"] for entry in report["mode_symmetry"])


def test_compare_detects_a_changed_case(tmp_path):
    baseline = tmp_path / "baseline.json"
    assert hook_timing_probe.main(["--quiet", "--dump", str(baseline)]) == 0

    report = json.loads(baseline.read_text(encoding="utf-8"))
    report["cases"][3]["events"][2]["text"] = "tampered"
    baseline.write_bytes(
        (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )

    assert hook_timing_probe.main(["--quiet", "--compare", str(baseline)]) == 1


def test_compare_reports_a_missing_baseline_as_usage_error(tmp_path):
    assert hook_timing_probe.main(["--compare", str(tmp_path / "nope.json")]) == 2
