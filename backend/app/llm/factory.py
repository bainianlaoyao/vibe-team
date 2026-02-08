from __future__ import annotations

from app.core.config import Settings
from app.db.enums import LLMProvider
from app.llm.contracts import LLMClient
from app.llm.errors import LLMErrorCode, LLMProviderError
from app.llm.providers.claude_code import CLAUDE_PROVIDER_NAME, ClaudeCodeAdapter


def create_llm_client(*, provider: str | LLMProvider, settings: Settings) -> LLMClient:
    """
    Create and return an LLM client for the specified provider.

    Args:
        provider: The LLM provider identifier (e.g., "anthropic", "claude_code").
                  Accepts LLMProvider enum or string.
        settings: Application settings containing provider configuration.

    Returns:
        LLMClient: An initialized LLM client adapter.

    Raises:
        LLMProviderError: If the provider is not supported.
    """
    if isinstance(provider, LLMProvider):
        normalized_provider = provider.value
    else:
        normalized_provider = provider.strip().lower()

    if normalized_provider == LLMProvider.ANTHROPIC or normalized_provider == CLAUDE_PROVIDER_NAME:
        return ClaudeCodeAdapter(
            settings_path=settings.claude_settings_path,
            cli_path=settings.claude_cli_path,
            default_max_turns=settings.claude_default_max_turns,
        )

    raise LLMProviderError(
        code=LLMErrorCode.UNSUPPORTED_PROVIDER,
        provider=str(provider),
        message=f"Unsupported LLM provider: {provider}.",
        retryable=False,
    )
