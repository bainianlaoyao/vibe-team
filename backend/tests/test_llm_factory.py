from __future__ import annotations

import pytest

from app.core.config import Settings
from app.llm.errors import LLMErrorCode, LLMProviderError
from app.llm.factory import create_llm_client
from app.llm.providers import ClaudeCodeAdapter


def test_factory_returns_claude_adapter_for_claude_code_provider() -> None:
    settings = Settings()
    client = create_llm_client(provider="claude_code", settings=settings)
    assert isinstance(client, ClaudeCodeAdapter)


def test_factory_returns_claude_adapter_for_anthropic_alias() -> None:
    settings = Settings()
    client = create_llm_client(provider="anthropic", settings=settings)
    assert isinstance(client, ClaudeCodeAdapter)


def test_factory_rejects_unsupported_provider() -> None:
    settings = Settings()
    with pytest.raises(LLMProviderError) as exc_info:
        create_llm_client(provider="openai", settings=settings)

    assert exc_info.value.code == LLMErrorCode.UNSUPPORTED_PROVIDER
