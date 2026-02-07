from __future__ import annotations

from app.core.config import Settings
from app.llm.contracts import LLMClient
from app.llm.errors import LLMErrorCode, LLMProviderError
from app.llm.providers.claude_code import CLAUDE_PROVIDER_NAME, ClaudeCodeAdapter


def create_llm_client(*, provider: str, settings: Settings) -> LLMClient:
    normalized_provider = provider.strip().lower()
    if normalized_provider in {CLAUDE_PROVIDER_NAME, "anthropic"}:
        return ClaudeCodeAdapter(
            settings_path=settings.claude_settings_path,
            cli_path=settings.claude_cli_path,
            default_max_turns=settings.claude_default_max_turns,
        )

    raise LLMProviderError(
        code=LLMErrorCode.UNSUPPORTED_PROVIDER,
        provider=provider,
        message=f"Unsupported LLM provider: {provider}.",
        retryable=False,
    )
