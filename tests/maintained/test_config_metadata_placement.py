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

from astrbot.core.config.default import (
    CONFIG_METADATA_2,
    CONFIG_METADATA_3,
    CONFIG_METADATA_3_SYSTEM,
)

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
    "与官方原版一致",
    "本维护版",
    "改回跟随官方",
    "matches upstream",
    "same as stock astrbot",
    "公式版と同一",
    "公式版と同じ",
    "как в официальной версии",
    "как в оригинале",
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
        ("CONFIG_METADATA_2", CONFIG_METADATA_2),
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


def _locale_node(data: dict, section: str, group: str, field_path: str):
    """Resolve a dotted metadata key into the nested locale bundle."""
    node = data.get(section, {}).get(group, {})
    for part in field_path.split("."):
        node = node.get(part, {}) if isinstance(node, dict) else {}
    return node


def test_every_field_resolves_in_every_locale():
    """A moved field is invisible until its i18n path moves with it.

    The bundle mirrors dotted metadata keys as nested objects. Copying a
    neighbouring field's layout once put the tool list under
    ``provider_settings.proactive_capability`` instead of
    ``agent_runner.config.misc``; the description never resolved and the field
    vanished from the form. This walks every declared string, not just ours.
    """
    fields = []
    for section, group, spec in _groups(CONFIG_METADATA_3):
        for path, value in _declarations(spec.get("items") or {}):
            for attr in ("description", "hint", "subtitles"):
                if attr in value:
                    fields.append((section, group, path, attr))

    assert fields, "the schema no longer declares any translatable copy"

    for locale in CONFIG_LOCALES:
        path = LOCALE_DIR / locale / "features" / "config-metadata.json"
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        for section, group, field_path, attr in fields:
            node = _locale_node(data, section, group, field_path)
            assert attr in node, (locale, section, group, field_path, attr)


def test_every_select_has_option_labels_in_every_locale():
    """A select without translated labels falls back to raw option values.

    The metadata converter replaces ``labels`` with an i18n key. An unmapped key
    is exactly how ``legacy`` / ``strict`` reached the panel next to a perfectly
    translated description, so every declared select is checked against all
    four bundles.
    """
    selects: list[tuple[str, str, str, int]] = []
    for section, group, spec in _groups(CONFIG_METADATA_3):
        for path, value in _declarations(spec.get("items") or {}):
            if "labels" in value:
                selects.append((section, group, path, len(value["labels"])))

    assert selects, "the schema no longer declares any labelled select"

    for locale in CONFIG_LOCALES:
        path = LOCALE_DIR / locale / "features" / "config-metadata.json"
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        for section, group, field_path, count in selects:
            node = _locale_node(data, section, group, field_path)
            labels = node.get("labels") if isinstance(node, dict) else None
            assert isinstance(labels, list) and len(labels) == count, (
                locale,
                section,
                group,
                field_path,
                labels,
            )
