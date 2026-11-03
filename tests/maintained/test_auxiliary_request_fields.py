"""Every auxiliary provider call must forward the request's extra parts.

Two closing calls in the agent loop (source-delivery correction, tool-failure
limit) send a second request for the same turn. They were built by copying the
main call and trimming it, and the trim took ``extra_user_content_parts`` with
it: quoted text, image notes and memory injections silently vanished from the
model's view, with nothing in the output to show they were missing.

The check is source-level on purpose. These calls sit deep inside async flows,
so a behavioural stand-in would be larger than the code under test; the defect
is a missing keyword, which is exactly what an AST walk sees. It also guards
future call sites -- a new trimmed call fails here instead of in production.
"""

from __future__ import annotations

import ast
from pathlib import Path

MODULE = (
    Path(__file__).resolve().parents[2]
    / "astrbot/core/agent/runners/tool_loop_agent_runner.py"
)


def test_auxiliary_text_chat_calls_forward_extra_parts() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    missing: list[int] = []

    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "text_chat"
        ):
            continue
        keywords = {kw.arg for kw in node.keywords if kw.arg}
        if not keywords:
            # ``text_chat(**payload)``: assembled elsewhere, covered by behaviour.
            continue
        if "contexts" in keywords and "extra_user_content_parts" not in keywords:
            missing.append(node.lineno)

    assert missing == [], (
        "text_chat calls that rebuild the turn must keep its extra parts; "
        f"missing at lines {missing}"
    )
