"""Surface checks for the additive API modules.

Verifies that the five documented modules import cleanly, export exactly the
contracted names, and never leak the internal bridge into the public surface.
"""

import astrbot.api._bridge as bridge
import astrbot.api.content as content
import astrbot.api.delivery as delivery
import astrbot.api.embedding as embedding
import astrbot.api.media as media
import astrbot.api.permissions as permissions
import astrbot.api.proactive as proactive
import astrbot.api.runtime as runtime
import astrbot.api.turns as turns

EXPECTED_ALL = {
    "media": {
        "IMAGE_CAPTION_MARKER",
        "IMAGE_INPUT_UNAVAILABLE_MESSAGE",
        "IMAGE_INPUT_UNAVAILABLE_NOTICE",
        "available",
        "has_image_caption",
        "has_visual_input",
        "image_input_available",
    },
    "turns": {
        "available",
        "is_current",
        "mark_sent",
        "merged_image_urls",
        "merged_text",
        "reset",
        "reset_all",
        "turn_version",
    },
    "delivery": {
        "CODE_DELIVERY_FAILURE",
        "available",
        "code_task_spec",
        "has_code_delivery",
    },
    "permissions": {
        "EXECUTION_NOT_AUTHORIZED",
        "available",
        "execution_denial",
        "is_admin",
    },
    "proactive": {
        "available",
        "generate_with_persona",
        "is_lightweight_proactive",
        "persona_available",
        "proactive_switch_is_disabled",
    },
    "content": {
        "ImageURLPart",
        "TextPart",
        "available",
        "is_image_part",
        "is_text_part",
    },
    "runtime": {
        "HOOK_TIMING_ENHANCED",
        "HOOK_TIMING_LEGACY",
        "available",
        "download_image_by_url",
        "extract_quoted_message_images",
        "get_astrbot_data_path",
        "hook_timing_mode",
    },
    "embedding": {
        "EmbeddingProvider",
        "available",
        "is_embedding_provider",
    },
}

MODULES = {
    "media": media,
    "turns": turns,
    "delivery": delivery,
    "permissions": permissions,
    "proactive": proactive,
    "content": content,
    "runtime": runtime,
    "embedding": embedding,
}

CAPABILITY_KEYS = {
    "turns.direct_turn",
    "delivery.code_policy",
    "permissions.execution_policy",
    "proactive.lightweight",
    "proactive.persona",
    "media.unavailable_contract",
    "content.parts",
    "runtime.helpers",
    "embedding.provider",
}


def test_all_declared_names_exist():
    for name, module in MODULES.items():
        for symbol in sorted(EXPECTED_ALL[name]):
            assert hasattr(module, symbol), f"{name}.{symbol} is missing"


def test_dunder_all_matches_contract():
    for name, module in MODULES.items():
        assert set(module.__all__) == EXPECTED_ALL[name], name


def test_dunder_all_is_sorted_and_unique():
    for name, module in MODULES.items():
        assert module.__all__ == sorted(module.__all__), name


def test_bridge_is_not_public():
    for name, module in MODULES.items():
        assert "_bridge" not in module.__all__, name
    assert bridge.__all__ == []


def test_capabilities_report_covers_contract():
    report = bridge.capabilities()
    assert set(report) == CAPABILITY_KEYS
    assert all(isinstance(value, bool) for value in report.values())


def test_resolve_returns_default_for_unknown_symbol():
    sentinel = object()
    resolved = bridge.resolve(
        "astrbot.core.utils.direct_turns", "_missing_name", sentinel
    )
    assert resolved is sentinel


def test_resolve_returns_default_for_unknown_module():
    sentinel = object()
    resolved = bridge.resolve("astrbot.core.no_such_module", "anything", sentinel)
    assert resolved is sentinel
