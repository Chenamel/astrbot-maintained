"""Known upstream test deviations (P11) for the maintained AstrBot fork.

This module is the single source of truth for the upstream tests this fork fails
**on purpose**. Every entry maps a pytest node id to a ``(group, reason)`` pair:

``alpha``
    Execution-tool authorisation tightening. **Reverted on purpose on
    2026-10-17 (T8-15)**: the tightening is now a mode
    (``provider_settings.execution_gate_mode``) that defaults to ``legacy``, so
    the default run matches upstream again and this group holds **no entry**.
    The behaviour is still available by opting into ``strict``; see
    ``docs/maintained/inventory.md`` section "α 组回退".
``beta``
    Agent-completion hook timing. **Reverted on purpose on 2026-10-18 (T8-16)**:
    the mode now defaults to ``legacy``, so the default run matches upstream and
    this group holds **no entry**. The improved timing stays available through
    ``agent_runner.config.misc.hook_timing_mode = enhanced`` and the code path
    must never be deleted by an upstream merge; see
    ``docs/maintained/inventory.md`` section "β 组回退 / α 组回退".

The root ``conftest.py`` turns each registered node id into an
``xfail(strict=True)`` marker: the test still runs, an expected failure is
reported as ``xfailed``, and an unexpected pass becomes ``XPASS(strict)``, which
fails the suite. That last property is the alarm for "this deviation was
reverted or overwritten by an upstream merge".

Adding an entry:
    Document the reason in ``docs/maintained/inventory.md`` section 4 (P11)
    first, then register it here.

Removing an entry:
    Only allowed when the deviation was intentionally reverted, with the reason
    recorded in the inventory. Otherwise the strict marker keeps the suite red.
"""

from __future__ import annotations

#: Deviation group for the intentional execution-tool authorisation tightening.
ALPHA = "alpha"

#: Deviation group for the intentional agent-completion hook timing improvement.
BETA = "beta"

_ALPHA_REASON = (
    "alpha (design): apply_execution_policy() tightens execution-tool "
    "authorisation, so this fork withholds the execute tools that upstream "
    "expects to be present."
)

_BETA_REASON = (
    "beta (design, architectural): the agent-completion hook fires before the "
    "reply is emitted, so reply pre-audit can intervene first. This fork keeps "
    "the improved timing on purpose and must not be reverted to upstream."
)

DEVIATIONS: dict[str, tuple[str, str]] = {
    # Both groups are empty: the alpha tightening and the beta hook timing are
    # opt-in modes now, so the default run matches upstream on every test.
}

#: Node ids marked with ``xfail`` during the current pytest session.
#:
#: The root ``conftest.py`` appends every node id it marks. The guard test in
#: ``tests/maintained/test_p11_deviations.py`` asserts that all registered
#: deviations were matched, so a silent miss (renamed test or changed
#: parametrisation)
#: cannot go unnoticed.
APPLIED: list[str] = []


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
