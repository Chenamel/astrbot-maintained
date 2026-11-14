"""Registry of expected failures in the upstream test suite.

This module is the single source of truth for the tests expected to fail here.
Every entry maps a pytest node id to a ``(group, reason)`` pair:

``alpha``
    Execution-tool authorisation tightening. Available as a mode
    (``provider_settings.execution_gate_mode``) that defaults to ``legacy``,
    so the default run holds no entry in this group. The behaviour stays
    available by opting into ``strict``; see the ``inventory`` document
    ("α 组回退"), resolved through ``doc_paths``.
``beta``
    Agent-completion hook timing. The mode defaults to ``legacy``, so the
    default run holds no entry in this group. The alternative timing stays
    available through ``agent_runner.config.misc.hook_timing_mode = enhanced``
    and must not be removed by a runner refactor; see the ``inventory``
    document ("β 组回退 / α 组回退"), resolved through ``doc_paths``.
``config``
    Extra defaults under ``agent_runner.config.misc``. The test migrates that
    mapping and compares it by **exact equality**, so the two extra keys
    (``hook_timing_mode``, ``lightweight_proactive_tools``) fail the assertion
    even though both defaults are inert unless opted into. This is a
    schema-shape difference, not a behaviour difference; see the
    ``inventory`` document, section 4 (P11).

The root ``conftest.py`` turns each registered node id into an
``xfail(strict=True)`` marker: the test still runs, an expected failure is
reported as ``xfailed``, and an unexpected pass becomes ``XPASS(strict)``,
which fails the suite. That last property raises the alarm once a registered
deviation stops being true.

Adding an entry:
    Document the reason in the ``inventory`` document, section 4 (P11), first,
    then register it here.

Removing an entry:
    Only allowed when the deviation was intentionally reverted, with the reason
    recorded in the inventory. Otherwise the strict marker keeps the suite red.
"""

from __future__ import annotations

#: Deviation group for the intentional execution-tool authorisation tightening.
ALPHA = "alpha"

#: Deviation group for the intentional agent-completion hook timing improvement.
BETA = "beta"

#: Deviation group for the extra ``agent_runner.config.misc`` defaults.
CONFIG = "config"

_ALPHA_REASON = (
    "alpha (design): apply_execution_policy() tightens execution-tool "
    "authorisation, so the execute tools the upstream suite expects are "
    "withheld."
)

_BETA_REASON = (
    "beta (design, architectural): the agent-completion hook fires before the "
    "reply is emitted, so reply pre-audit can intervene first. The timing is "
    "deliberate and must survive runner refactors."
)

_CONFIG_REASON = (
    "config (schema shape): `agent_runner.config.misc` declares "
    "`hook_timing_mode` and `lightweight_proactive_tools`. This test migrates "
    "that mapping and compares it by exact equality, so the two extra defaults "
    "fail it even though both are inert unless a config opts in."
)

DEVIATIONS: dict[str, tuple[str, str]] = {
    # Alpha and beta are empty: both are opt-in modes, so the default run
    # needs no deviation in those groups.
    "tests/unit/test_agent_runner_config.py"
    "::test_local_legacy_fields_are_fully_migrated": (CONFIG, _CONFIG_REASON),
    "tests/unit/test_agent_runner_config.py"
    "::test_local_migration_replaces_default_root_inserted_before_version_bump": (
        CONFIG,
        _CONFIG_REASON,
    ),
}

#: Node ids marked with ``xfail`` during the current pytest session.
#:
#: The root ``conftest.py`` appends every node id it marks. The guard test in
#: ``tests/maintained/test_p11_deviations.py`` asserts that all registered
#: deviations were matched, so a silent miss (renamed test or changed
#: parametrisation)
#: cannot go unnoticed.
APPLIED: list[str] = []

#: Statements the project's protected deviations must keep saying, verbatim.
#:
#: Maintainer-only documents (``.internal/``) are absent from a fresh clone,
#: so a guard reading them could only be satisfied on the maintainer's machine
#: and would either fail or be skipped elsewhere -- silently removing the alarm
#: it exists to raise. The red line is a property of the code, so it is declared
#: here, in a file git tracks, and the guard asserts against this table.
#:
#: Each entry is ``(document key, phrase, why it must stay)``. The phrase is
#: checked against ``maintained/doc_paths`` when that document is present, so the
#: prose and the code cannot drift apart while still being editable in place.
PROTECTED_RED_LINES: tuple[tuple[str, str, str], ...] = (
    (
        "inventory",
        "坚决不改回上游",
        "beta: the improved hook timing is kept on purpose and must not be "
        "reverted to upstream",
    ),
    (
        "inventory",
        "核心架构优化",
        "beta: the timing change is an architectural decision, not an accident",
    ),
    (
        "project_rules",
        "合并红线",
        "the merge rule that protects beta when upstream conflicts with it",
    ),
    (
        "project_rules",
        "P11",
        "the registry this module implements; the rules document must name it",
    ),
)


def reason_for(node_id: str) -> tuple[str, str] | None:
    """Return the deviation registered for a pytest node id.

    Args:
        node_id: Node id as reported by pytest, for example
            ``tests/unit/test_x.py::test_y[True-local-cron]``. Path separators
            may be either slash or backslash.

    Returns:
        The registered ``(group, reason)`` pair, or ``None`` when the test is
        not a known deviation.
    """
    key = node_id.replace("\\", "/")
    entry = DEVIATIONS.get(key)
    if entry is not None:
        return entry
    # Fall back to matching the tail (``Class::test_name[params]``) so a change
    # in how pytest renders the path prefix does not silently drop the marker.
    path, _, tail = key.partition("::")
    for registered, value in DEVIATIONS.items():
        registered_path, _, registered_tail = registered.partition("::")
        if registered_tail != tail:
            continue
        if (
            registered_path == path
            or registered_path.endswith("/" + path)
            or path.endswith("/" + registered_path)
        ):
            return value
    return None
