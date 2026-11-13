"""Where the maintained-only config fields live, and how they read.

Placement is not cosmetic: every one of these keys was originally dropped into
a group chosen because it was nearby in the file, not because a reader would
look there. Upstream later added an access-control section, which gave the
execution-authorization switch an obvious home. The tests pin the three homes
so a future merge cannot quietly move them back into a junk drawer.

The other half is voice. Early copy kept explaining that an option was added
by this branch and absent upstream. That is a note to the maintainer, not to
the person configuring a bot, and it does not belong in a form.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from astrbot.core.config.default import CONFIG_METADATA_3, CONFIG_METADATA_3_SYSTEM

ROOT = Path(__file__).resolve().parents[2]
LOCALE_DIR = ROOT / "dashboard" / "src" / "i18n" / "locales"
CONFIG_LOCALES = ("zh-CN", "en-US", "ja-JP", "ru-RU")

BANNED = (
    "本分支",
    "维护分支",
    "本 fork",
    "maintained fork",
    "本フォーク",
    "メンテナンスフォーク",
    "добавление форка",
    "этого форка",
)


def _declarations(node: dict):
    """Yield ``(key, spec)`` for every typed leaf in a metadata subtree."""
    for key, value in node.items():
        if not isinstance(value, dict):
            continue
        if value.get("type") == "object" and isinstance(value.get("items"), dict):
            yield from _declarations(value["items"])
        elif "type" in value:
            yield key, value


def _groups(meta: dict):
    """Yield ``(section, group, spec)`` for every group in a rendered tree."""
    for section, node in meta.items():
        for group, spec in (node.get("metadata") or {}).items():
            yield section, group, spec


def _copy(node) -> list[str]:
    """Return the user-visible strings of a metadata subtree."""
    out: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("description", "hint") and isinstance(value, str):
                out.append(value)
            elif key == "labels" and isinstance(value, list):
                out.extend(item for item in value if isinstance(item, str))
            else:
                out.extend(_copy(value))
    elif isinstance(node, list):
        for item in node:
            out.extend(_copy(item))
    return out


def test_maintained_only_fields_sit_in_named_groups():
    """Each switch belongs in a group a reader would actually open."""
    expected = {
        "execution_gate_mode": ("access_group", "tool_execution"),
        "lightweight_proactive_tools": ("ai_group", "proactive_capability"),
        "hook_timing_mode": ("plugin_group", "hooks"),
    }
    found: dict[str, list[tuple[str, str]]] = {}
    for section, group, spec in _groups(CONFIG_METADATA_3):
        for key, _ in _declarations(spec.get("items") or {}):
            found.setdefault(key.rsplit(".", 1)[-1], []).append((section, group))

    for key, home in expected.items():
        assert home in found.get(key, []), (key, found.get(key))


def test_the_tool_list_can_be_picked_from_the_registry():
    """The picker is opt-in through the schema, not a hard-coded field name."""
    group = CONFIG_METADATA_3["ai_group"]["metadata"]["proactive_capability"]
    spec = dict(_declarations(group.get("items") or {}))
    assert spec["agent_runner.config.misc.lightweight_proactive_tools"]["_special"] == (
        "select_tool"
    )


def test_config_copy_does_not_explain_the_branch():
    """Provenance notes belong in a commit message, not in a form."""
    for name, tree in (
        ("CONFIG_METADATA_3", CONFIG_METADATA_3),
        ("CONFIG_METADATA_3_SYSTEM", CONFIG_METADATA_3_SYSTEM),
    ):
        for text in _copy(tree):
            for phrase in BANNED:
                assert phrase.lower() not in text.lower(), (name, phrase, text[:80])

    for locale in CONFIG_LOCALES:
        path = LOCALE_DIR / locale / "features" / "config-metadata.json"
        parsed = json.loads(path.read_text(encoding="utf-8-sig"))
        for text in _copy(parsed):
            for phrase in BANNED:
                assert phrase.lower() not in text.lower(), (locale, phrase, text[:80])


def test_config_locale_files_have_no_duplicate_keys():
    """A duplicate key silently discards the earlier translation.

    Two copies of ``execution_gate_mode`` once sat in the same object; the
    second won, and it was the one carrying the provenance note.
    """
    for locale in CONFIG_LOCALES:
        path = LOCALE_DIR / locale / "features" / "config-metadata.json"
        duplicates: list[str] = []

        def detect(pairs):
            keys = [key for key, _ in pairs]
            duplicates.extend(key for key, n in Counter(keys).items() if n > 1)
            return dict(pairs)

        json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=detect)
        assert duplicates == [], (locale, duplicates)
