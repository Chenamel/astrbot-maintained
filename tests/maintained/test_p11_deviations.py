"""Guard the registry of intentional upstream deviations (P11).

The registry in ``maintained/p11_deviations.py`` is what makes "the suite is
green" a well-defined statement. Alpha and beta are empty since T8-15/T8-16
turned their behaviour into opt-in modes; the ``config`` group is not, because
the fork adds two defaults to a mapping upstream compares by exact equality.
These tests guard the registry itself -- a renamed upstream test, a watered-down
reason, a deleted red-line note, or a group whose count drifted must turn the
suite red instead of silently disabling the alarm.
"""

from __future__ import annotations

from pathlib import Path

import doc_paths
import p11_deviations
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Number of deviations per group (see the ``inventory`` document, section 4 P11).
#: Alpha and beta are zero since T8-15/T8-16 turned them into opt-in modes; the
#: config group holds the two exact-dict assertions our extra defaults break.
EXPECTED_COUNTS = {
    p11_deviations.ALPHA: 0,
    p11_deviations.BETA: 0,
    p11_deviations.CONFIG: 2,
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
    """The registry holds exactly the documented deviations.

    Alpha and beta stay empty: the tightening is reachable through
    ``execution_gate_mode=strict`` and the timing through
    ``hook_timing_mode=enhanced``. The config group is expected to hold two,
    and a third appearing there means someone added another default to
    ``agent_runner.config.misc`` without registering the test it breaks.
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


def test_beta_protection_is_declared_in_code():
    """The beta red line is asserted from code, not from a maintainer-only doc.

    The phrases used to be read straight out of ``inventory.md`` and
    ``project_rules.md``. Those documents are now maintainer-only (``.internal/``,
    gitignored), so a guard that needed them would fail -- or be skipped -- in a
    fresh clone of the published repository, quietly removing the alarm it exists
    to raise. The phrases therefore live in
    :data:`p11_deviations.PROTECTED_RED_LINES`, which git tracks.
    """
    declared = {phrase for _, phrase, _ in p11_deviations.PROTECTED_RED_LINES}
    assert "坚决不改回上游" in declared
    assert "核心架构优化" in declared
    assert "合并红线" in declared
    assert "P11" in declared

    for name, phrase, why in p11_deviations.PROTECTED_RED_LINES:
        assert why.strip(), f"{phrase} must say why it is protected"
        assert len(why) > 20, f"{phrase} needs a real reason, not a label"
        assert name in doc_paths.DOCUMENTS, f"undeclared document: {name}"


def test_the_declared_red_lines_are_still_written_down():
    """Every declared phrase still appears in the document that states it.

    Skipped -- not failed -- when the document is absent: a fresh clone of the
    published repository has no ``.internal/`` tree, and absence of a
    maintainer-only note is not a defect. The alarm lives in
    ``test_beta_protection_is_declared_in_code``, which needs no document.
    """
    missing = [name for name in doc_paths.DOCUMENTS if doc_paths.path(name) is None]
    if missing:
        pytest.skip(f"maintainer-only documents not present: {', '.join(missing)}")

    for name, phrase, _ in p11_deviations.PROTECTED_RED_LINES:
        text = doc_paths.read(name)
        assert text is not None, name
        assert phrase in text, f"{name} no longer says {phrase!r}"


def test_core_anchors_of_both_groups_are_present():
    """Both deviations still have the core code they are attributed to."""
    alpha_source = (REPO_ROOT / ALPHA_ANCHOR_FILE).read_text(encoding="utf-8")
    beta_source = (REPO_ROOT / BETA_ANCHOR_FILE).read_text(encoding="utf-8")
    assert ALPHA_ANCHOR_TEXT in alpha_source
    assert BETA_ANCHOR_TEXT in beta_source


def test_every_deviation_was_matched_when_upstream_runs():
    """When the upstream files are collected, every marker must be applied.

    Running only ``tests/maintained`` collects no deviation, so the check is
    skipped; running the upstream files collects them and a silent miss (renamed
    test, changed parametrisation) must fail here.
    """
    applied = p11_deviations.APPLIED
    if not applied:
        pytest.skip("no upstream deviation collected in this session")
    assert len(applied) == len(p11_deviations.DEVIATIONS)
    assert set(applied) == set(p11_deviations.DEVIATIONS)
