"""Per-call ``extra_body`` must reach the provider payload.

Providers build their request payload from fixed arguments, so a caller could
not tweak a single request (for example to disable thinking) without editing the
shared provider config -- which also affects every other caller of that provider.
``_prepare_chat_payload`` now merges a caller-supplied ``extra_body`` last, and
the downstream query layer already forwards unknown payload keys to the API.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.provider.sources.openai_responses_source import (
    ProviderOpenAIResponses,
)


def _bare_provider() -> ProviderOpenAIResponses:
    """Build an instance without running the real constructor."""
    provider = object.__new__(ProviderOpenAIResponses)
    provider.provider_config = {"model": "test-model"}
    provider.client = MagicMock()
    provider._ensure_message_to_dicts = lambda contexts: []
    provider.get_model = lambda: "test-model"
    provider._context_contains_image = lambda query: False
    provider.assemble_context = AsyncMock(
        return_value={"role": "user", "content": "hi"}
    )
    return provider


@pytest.mark.asyncio
async def test_extra_body_is_merged_into_payloads():
    provider = _bare_provider()

    payloads, _ = await provider._prepare_chat_payload(
        prompt="hi", extra_body={"reasoning": {"effort": "none"}}
    )

    assert payloads["reasoning"] == {"effort": "none"}


@pytest.mark.asyncio
async def test_extra_body_can_override_a_default_field():
    """Merged last on purpose: a caller may override for this request only."""
    provider = _bare_provider()

    payloads, _ = await provider._prepare_chat_payload(
        prompt="hi", extra_body={"model": "other-model"}
    )

    assert payloads["model"] == "other-model"


@pytest.mark.asyncio
async def test_absent_or_invalid_extra_body_changes_nothing():
    provider = _bare_provider()

    baseline, _ = await provider._prepare_chat_payload(prompt="hi")
    with_garbage, _ = await provider._prepare_chat_payload(
        prompt="hi", extra_body="not-a-dict"
    )

    assert baseline == with_garbage
    assert "reasoning" not in baseline
