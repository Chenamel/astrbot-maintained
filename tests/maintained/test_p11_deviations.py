"""Guard the registry of intentional upstream deviations (P11).

The registry in ``maintained/p11_deviations.py`` is what makes "the suite is
green" a well-defined statement. Both groups are empty since T8-15 and T8-16
turned their behaviour into opt-in modes, so the default run matches upstream on
every test. These tests guard the registry itself -- a renamed upstream test, a
watered-down reason, or a deleted red-line note must turn the suite red instead
of silently disabling the alarm.
"""

from __future__ import annotations

from pathlib import Path

import p11_deviations
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Number of deviations per group (see ``docs/maintained/inventory.md`` §4 P11).
#: Both groups are zero since T8-15/T8-16 turned them into opt-in modes.
EXPECTED_COUNTS = {
    p11_deviations.ALPHA: 0,
    p11_deviations.BETA: 0,
}

ALPHA_ANCHOR_FILE = Path("astrbot/core/astr_main_agent.py")
ALPHA_ANCHOR_TEXT = "apply_execution_policy("
BETA_ANCHOR_FILE = Path("astrbot/core/agent/runners/tool_loop_agent_runner.py")
BETA_ANCHOR_TEXT = "_complete_with_assistant_response"

NODE_IDS = sorted(p11_deviations.DEVIATIONS)


def _file_part(node_id: str) -> str:
    """Return the path part of a pytest node id."""
    return node_id.partition("::")[0]


def _test_name(node_id: str) -> str:
    """Return the test function name carried by a pytest node id."""
    tail = node_id.partition("::")[2]
    return tail.split("::")[-1].split("[")[0]


def test_registry_matches_the_documented_groups():
    """The registry holds exactly the documented alpha and beta deviations.

    Both groups stay empty: the alpha tightening is reachable through
    ``execution_gate_mode=strict`` and the beta timing through
    ``hook_timing_mode=enhanced``, so the default run keeps no deviation.
    """
    groups = [group for group, _ in p11_deviations.DEVIATIONS.values()]
    for group, expected in EXPECTED_COUNTS.items():
        assert groups.count(group) == expected, group
    assert len(p11_deviations.DEVIATIONS) == sum(EXPECTED_COUNTS.values())
    assert set(groups) <= set(EXPECTED_COUNTS)


@pytest.mark.parametrize("node_id", NODE_IDS)
def test_deviation_points_at_an_existing_upstream_test(node_id):
    """Every registered node id still resolves to a real upstream test."""
    relative_path = _file_part(node_id)
    path = REPO_ROOT / relative_path
    assert path.is_file(), f"missing upstream test file: {relative_path}"
    assert _test_name(node_id) in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("node_id", NODE_IDS)
def test_deviation_reason_names_its_group(node_id):
    """Every reason is non-empty and states which group it belongs to."""
    group, reason = p11_deviations.DEVIATIONS[node_id]
    assert reason.strip()
    assert group in reason
    assert len(reason) > 40


def test_beta_protection_is_documented():
    """The beta red line may not be edited away from the project docs."""
    inventory = (REPO_ROOT / "docs/maintained/inventory.md").read_text(encoding="utf-8")
    rules = (REPO_ROOT / "docs/maintained/project_rules.md").read_text(encoding="utf-8")
    assert "坚决不改回上游" in inventory
    assert "核心架构优化" in inventory
    assert "合并红线" in rules
    assert "P11" in rules


def test_core_anchors_of_both_groups_are_present():
    """Both deviations still have the core code they are attributed to."""
    alpha_source = (REPO_ROOT / ALPHA_ANCHOR_FILE).read_text(encoding="utf-8")
    beta_source = (REPO_ROOT / BETA_ANCHOR_FILE).read_text(encoding="utf-8")
    assert ALPHA_ANCHOR_TEXT in alpha_source
    assert BETA_ANCHOR_TEXT in beta_source


def test_every_deviation_was_matched_when_upstream_runs():
    """When the upstream files are collected, all 17 markers must be applied.

    Running only ``tests/maintained`` collects no deviation, so the check is
    skipped; running the upstream files collects them and a silent miss (renamed
    test, changed parametrisation) must fail here.
    """
    applied = p11_deviations.APPLIED
    if not applied:
        pytest.skip("no upstream deviation collected in this session")
    assert len(applied) == len(p11_deviations.DEVIATIONS)
    assert set(applied) == set(p11_deviations.DEVIATIONS)
