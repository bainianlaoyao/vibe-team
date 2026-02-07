from __future__ import annotations

from enum import StrEnum


class LLMErrorCode(StrEnum):
    INVALID_REQUEST = "invalid_request"
    PROVIDER_NOT_FOUND = "provider_not_found"
    AUTHENTICATION_FAILED = "authentication_failed"
    RATE_LIMITED = "rate_limited"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_PROTOCOL_ERROR = "provider_protocol_error"
    EXECUTION_FAILED = "execution_failed"
    CONTEXT_LIMIT_EXCEEDED = "context_limit_exceeded"
    CANCELLED = "cancelled"
    UNSUPPORTED_PROVIDER = "unsupported_provider"


class LLMProviderError(Exception):
    def __init__(
        self,
        *,
        code: LLMErrorCode,
        provider: str,
        message: str,
        retryable: bool,
        cause: Exception | None = None,
    ) -> None:
        self.code = code
        self.provider = provider
        self.message = message
        self.retryable = retryable
        self.cause = cause
        super().__init__(message)
