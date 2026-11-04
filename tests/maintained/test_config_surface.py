"""The fork's own config keys must be reachable and validated.

Two different schema trees drive the dashboard, and picking the wrong one is
silent: the key still saves, still takes effect, and simply never appears in any
form. That is how two of these five keys ended up editable only through the raw
JSON view.

* ``CONFIG_METADATA_3_SYSTEM`` -- the system-settings page (``/api/v1/system-config``).
* ``CONFIG_METADATA_3``        -- a bot's config profile (``/api/v1/config-profiles/<id>``).
* ``CONFIG_METADATA_2``        -- legacy API plus **the schema the save path
  validates against**; it renders nothing in the current UI.

So a key that lives only in ``_2`` has validation and no form; a key that lives
only in ``_3`` has a form and no validation. Each of these tests pins the
placement that was chosen, so moving one has to be deliberate.
"""

from __future__ import annotations

from astrbot.core.config.default import (
    CONFIG_METADATA_2,
    CONFIG_METADATA_3,
    CONFIG_METADATA_3_SYSTEM,
)
from astrbot.dashboard.services.config_service import validate_config


def _forward_refs(meta: dict, *, expect_keys: tuple[str, ...]) -> bool:
    """Return whether the expected keys are all declared with a real type.

    Args:
        meta: One metadata subtree, e.g. ``CONFIG_METADATA_3_SYSTEM``.
        expect_keys: Keys that must appear in a node that has both a ``type``
            and something to render (``description``) or validate.

    Returns:
        True when every expected key is present as a typed leaf.
    """
    found: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                # ``_3`` writes keys as dotted paths (``provider_settings.x``)
                # while ``_2`` nests them; compare the last segment so both work.
                leaf = key.rsplit(".", 1)[-1]
                if (
                    leaf in expect_keys
                    and isinstance(value, dict)
                    and "type" in value
                ):
                    found.add(leaf)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(meta)
    return found == set(expect_keys)


def test_system_settings_show_the_two_misc_keys():
    """``direct_turn_quiet_sec`` / ``log_escape_message_newlines`` belong here.

    Both are top-level settings with no other home; before this they were only
    in the legacy tree, which the current UI never requests.
    """
    assert _forward_refs(
        CONFIG_METADATA_3_SYSTEM,
        expect_keys=("direct_turn_quiet_sec", "log_escape_message_newlines"),
    )


def test_the_profile_tree_carries_the_agent_settings():
    """Agent-runner settings are per bot, so they live in the profile schema."""
    assert _forward_refs(
        CONFIG_METADATA_3,
        expect_keys=(
            "execution_gate_mode",
            "hook_timing_mode",
            "lightweight_proactive_tools",
        ),
    )


def test_the_profile_tree_shows_the_execution_gate():
    assert _forward_refs(CONFIG_METADATA_3, expect_keys=("execution_gate_mode",))


def test_the_legacy_tree_still_validates_the_execution_gate():
    """Only ``_2`` validates, so the key has to exist there as well.

    Without it the save path skips the key entirely -- unknown keys are ignored,
    not rejected -- and a hand-written ``"STRICT"`` reaches the runtime.
    """
    provider_settings = CONFIG_METADATA_2["provider_group"]["metadata"][
        "provider_settings"
    ]["items"]

    assert "execution_gate_mode" in provider_settings
    assert provider_settings["execution_gate_mode"]["options"] == ["legacy", "strict"]


def test_a_bad_execution_gate_value_is_rejected():
    """The point of declaring it in ``_2``: a wrong type stops at the door."""
    errors, _ = validate_config(
        {"provider_settings": {"execution_gate_mode": 123}},
        CONFIG_METADATA_2,
        True,
    )

    assert any("execution_gate_mode" in message for message in errors), errors


def test_a_known_execution_gate_value_passes():
    errors, _ = validate_config(
        {"provider_settings": {"execution_gate_mode": "strict"}},
        CONFIG_METADATA_2,
        True,
    )

    assert errors == []
