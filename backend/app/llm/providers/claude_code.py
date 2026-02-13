from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Protocol

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ClaudeSDKError,
    CLIConnectionError,
    CLIJSONDecodeError,
    CLINotFoundError,
    ProcessError,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

from app.llm.contracts import (
    LLMClient,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMToolCall,
    LLMUsage,
    StreamCallback,
    StreamEvent,
    StreamEventType,
)
from app.llm.errors import LLMErrorCode, LLMProviderError
from app.llm.providers.claude_settings import (
    resolve_claude_auth,
    resolve_claude_cli_path,
    resolve_claude_permission_mode,
)

CLAUDE_PROVIDER_NAME = "claude_code"
_COST_SCALE = Decimal("0.0001")


class ClaudeSDKClientLike(Protocol):
    async def query(self, prompt: str, session_id: str = "default") -> None: ...

    def receive_response(self) -> AsyncIterator[Any]: ...


ClaudeClientFactory = Callable[
    [ClaudeAgentOptions],
    AbstractAsyncContextManager[ClaudeSDKClientLike],
]


class ClaudeCodeAdapter(LLMClient):
    def __init__(
        self,
        *,
        settings_path: str | Path | None = None,
        cli_path: str | Path | None = None,
        default_max_turns: int | None = None,
        client_factory: ClaudeClientFactory | None = None,
    ) -> None:
        self._settings_path = settings_path
        self._cli_path = resolve_claude_cli_path(cli_path)
        self._default_max_turns = default_max_turns
        self._client_factory = client_factory or (lambda options: ClaudeSDKClient(options=options))

    async def generate(self, request: LLMRequest) -> LLMResponse:
        prompt = _extract_last_user_prompt(request.messages)
        auth = resolve_claude_auth(settings_path_override=self._settings_path)
        options = ClaudeAgentOptions(
            model=request.model,
            system_prompt=request.system_prompt,
            max_turns=request.max_turns or self._default_max_turns,
            permission_mode=resolve_claude_permission_mode(),
            cwd=request.cwd,
            settings=str(auth.settings_path) if auth.settings_path else None,
            env=auth.env,
            cli_path=self._cli_path,
        )

        try:
            async with self._client_factory(options) as client:
                await client.query(prompt, session_id=request.session_id)
                return await _collect_response(
                    client=client,
                    provider=request.provider,
                    model=request.model,
                    session_id=request.session_id,
                )
        except LLMProviderError:
            raise
        except CLINotFoundError as exc:
            raise LLMProviderError(
                code=LLMErrorCode.PROVIDER_NOT_FOUND,
                provider=request.provider,
                message=str(exc),
                retryable=False,
                cause=exc,
            ) from exc
        except CLIConnectionError as exc:
            raise LLMProviderError(
                code=LLMErrorCode.PROVIDER_UNAVAILABLE,
                provider=request.provider,
                message=str(exc),
                retryable=True,
                cause=exc,
            ) from exc
        except CLIJSONDecodeError as exc:
            raise LLMProviderError(
                code=LLMErrorCode.PROVIDER_PROTOCOL_ERROR,
                provider=request.provider,
                message=str(exc),
                retryable=True,
                cause=exc,
            ) from exc
        except ProcessError as exc:
            raise LLMProviderError(
                code=LLMErrorCode.EXECUTION_FAILED,
                provider=request.provider,
                message=str(exc),
                retryable=True,
                cause=exc,
            ) from exc
        except ClaudeSDKError as exc:
            raise LLMProviderError(
                code=LLMErrorCode.EXECUTION_FAILED,
                provider=request.provider,
                message=str(exc),
                retryable=True,
                cause=exc,
            ) from exc

    async def generate_stream(
        self,
        request: LLMRequest,
        callback: StreamCallback,
    ) -> LLMResponse:
        """Generate response with streaming callbacks for real-time updates."""
        prompt = _extract_last_user_prompt(request.messages)
        auth = resolve_claude_auth(settings_path_override=self._settings_path)
        options = ClaudeAgentOptions(
            model=request.model,
            system_prompt=request.system_prompt,
            max_turns=request.max_turns or self._default_max_turns,
            permission_mode=resolve_claude_permission_mode(),
            cwd=request.cwd,
            settings=str(auth.settings_path) if auth.settings_path else None,
            env=auth.env,
            cli_path=self._cli_path,
        )

        try:
            async with self._client_factory(options) as client:
                await client.query(prompt, session_id=request.session_id)
                return await _collect_response_streaming(
                    client=client,
                    provider=request.provider,
                    model=request.model,
                    session_id=request.session_id,
                    callback=callback,
                )
        except LLMProviderError:
            raise
        except CLINotFoundError as exc:
            await callback(
                StreamEvent(
                    event_type=StreamEventType.ERROR,
                    error=str(exc),
                )
            )
            raise LLMProviderError(
                code=LLMErrorCode.PROVIDER_NOT_FOUND,
                provider=request.provider,
                message=str(exc),
                retryable=False,
                cause=exc,
            ) from exc
        except CLIConnectionError as exc:
            await callback(
                StreamEvent(
                    event_type=StreamEventType.ERROR,
                    error=str(exc),
                )
            )
            raise LLMProviderError(
                code=LLMErrorCode.PROVIDER_UNAVAILABLE,
                provider=request.provider,
                message=str(exc),
                retryable=True,
                cause=exc,
            ) from exc
        except CLIJSONDecodeError as exc:
            await callback(
                StreamEvent(
                    event_type=StreamEventType.ERROR,
                    error=str(exc),
                )
            )
            raise LLMProviderError(
                code=LLMErrorCode.PROVIDER_PROTOCOL_ERROR,
                provider=request.provider,
                message=str(exc),
                retryable=True,
                cause=exc,
            ) from exc
        except ProcessError as exc:
            await callback(
                StreamEvent(
                    event_type=StreamEventType.ERROR,
                    error=str(exc),
                )
            )
            raise LLMProviderError(
                code=LLMErrorCode.EXECUTION_FAILED,
                provider=request.provider,
                message=str(exc),
                retryable=True,
                cause=exc,
            ) from exc
        except ClaudeSDKError as exc:
            await callback(
                StreamEvent(
                    event_type=StreamEventType.ERROR,
                    error=str(exc),
                )
            )
            raise LLMProviderError(
                code=LLMErrorCode.EXECUTION_FAILED,
                provider=request.provider,
                message=str(exc),
                retryable=True,
                cause=exc,
            ) from exc


def _extract_last_user_prompt(messages: list[LLMMessage]) -> str:
    for message in reversed(messages):
        if message.role.value == "user":
            content = message.content.strip()
            if content:
                return content
    raise LLMProviderError(
        code=LLMErrorCode.INVALID_REQUEST,
        provider=CLAUDE_PROVIDER_NAME,
        message="LLMRequest.messages must include at least one non-empty user message.",
        retryable=False,
    )


async def _collect_response(
    *,
    client: ClaudeSDKClientLike,
    provider: str,
    model: str | None,
    session_id: str,
) -> LLMResponse:
    text_parts: list[str] = []
    tool_calls: list[LLMToolCall] = []
    final_result: ResultMessage | None = None
    assistant_error: str | None = None

    async for message in client.receive_response():
        if isinstance(message, AssistantMessage):
            if message.error is not None:
                assistant_error = message.error
            for block in message.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)
                if isinstance(block, ToolUseBlock):
                    tool_calls.append(
                        LLMToolCall(id=block.id, name=block.name, arguments=dict(block.input))
                    )
            continue

        if isinstance(message, ResultMessage):
            final_result = message

    if assistant_error is not None:
        raise _map_assistant_error(provider=provider, assistant_error=assistant_error)

    if final_result is None:
        raise LLMProviderError(
            code=LLMErrorCode.PROVIDER_PROTOCOL_ERROR,
            provider=provider,
            message="Claude SDK response stream ended without ResultMessage.",
            retryable=True,
        )

    if final_result.is_error:
        raise _map_result_error(provider=provider, result=final_result)

    text = "".join(text_parts).strip()
    if not text and final_result.result:
        text = final_result.result.strip()

    usage = _extract_usage(provider=provider, result=final_result)
    return LLMResponse(
        provider=provider,
        model=model,
        session_id=final_result.session_id or session_id,
        text=text,
        tool_calls=tool_calls,
        usage=usage,
        stop_reason=final_result.subtype,
        raw_result=final_result.result,
    )


async def _collect_response_streaming(
    *,
    client: ClaudeSDKClientLike,
    provider: str,
    model: str | None,
    session_id: str,
    callback: StreamCallback,
) -> LLMResponse:
    """Collect response while streaming events via callback."""
    text_parts: list[str] = []
    tool_calls: list[LLMToolCall] = []
    final_result: ResultMessage | None = None
    assistant_error: str | None = None

    async for message in client.receive_response():
        if isinstance(message, AssistantMessage):
            if message.error is not None:
                assistant_error = message.error
                await callback(
                    StreamEvent(
                        event_type=StreamEventType.ERROR,
                        error=message.error,
                    )
                )
            for block in message.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)
                    await callback(
                        StreamEvent(
                            event_type=StreamEventType.TEXT_CHUNK,
                            content=block.text,
                        )
                    )
                if isinstance(block, ToolUseBlock):
                    tool_call = LLMToolCall(
                        id=block.id, name=block.name, arguments=dict(block.input)
                    )
                    tool_calls.append(tool_call)
                    await callback(
                        StreamEvent(
                            event_type=StreamEventType.TOOL_CALL_START,
                            tool_call=tool_call,
                        )
                    )
            continue

        if isinstance(message, ResultMessage):
            final_result = message

    if assistant_error is not None:
        raise _map_assistant_error(provider=provider, assistant_error=assistant_error)

    if final_result is None:
        raise LLMProviderError(
            code=LLMErrorCode.PROVIDER_PROTOCOL_ERROR,
            provider=provider,
            message="Claude SDK response stream ended without ResultMessage.",
            retryable=True,
        )

    if final_result.is_error:
        await callback(
            StreamEvent(
                event_type=StreamEventType.ERROR,
                error=final_result.result or "Unknown error",
            )
        )
        raise _map_result_error(provider=provider, result=final_result)

    text = "".join(text_parts).strip()
    if not text and final_result.result:
        text = final_result.result.strip()

    usage = _extract_usage(provider=provider, result=final_result)

    # Send complete event with usage info
    await callback(
        StreamEvent(
            event_type=StreamEventType.COMPLETE,
            usage=usage,
        )
    )

    return LLMResponse(
        provider=provider,
        model=model,
        session_id=final_result.session_id or session_id,
        text=text,
        tool_calls=tool_calls,
        usage=usage,
        stop_reason=final_result.subtype,
        raw_result=final_result.result,
    )


def _extract_usage(*, provider: str, result: ResultMessage) -> LLMUsage:
    usage_payload = result.usage or {}

    token_in = (
        _read_usage_int(provider=provider, usage_payload=usage_payload, field_name="input_tokens")
        + _read_usage_int(
            provider=provider,
            usage_payload=usage_payload,
            field_name="cache_creation_input_tokens",
        )
        + _read_usage_int(
            provider=provider,
            usage_payload=usage_payload,
            field_name="cache_read_input_tokens",
        )
    )
    token_out = _read_usage_int(
        provider=provider,
        usage_payload=usage_payload,
        field_name="output_tokens",
    )
    cost_usd = _normalize_cost(result.total_cost_usd)
    return LLMUsage(
        request_count=1,
        token_in=token_in,
        token_out=token_out,
        cost_usd=cost_usd,
    )


def _read_usage_int(
    *,
    provider: str,
    usage_payload: dict[str, Any],
    field_name: str,
) -> int:
    raw_value = usage_payload.get(field_name, 0)
    if raw_value is None:
        return 0
    if isinstance(raw_value, bool):
        raise LLMProviderError(
            code=LLMErrorCode.PROVIDER_PROTOCOL_ERROR,
            provider=provider,
            message=f"Invalid usage field {field_name}: boolean is not allowed.",
            retryable=True,
        )

    if isinstance(raw_value, int):
        if raw_value < 0:
            raise LLMProviderError(
                code=LLMErrorCode.PROVIDER_PROTOCOL_ERROR,
                provider=provider,
                message=f"Invalid usage field {field_name}: negative value {raw_value}.",
                retryable=True,
            )
        return raw_value

    if isinstance(raw_value, float):
        if raw_value < 0 or not raw_value.is_integer():
            raise LLMProviderError(
                code=LLMErrorCode.PROVIDER_PROTOCOL_ERROR,
                provider=provider,
                message=f"Invalid usage field {field_name}: non-integer value {raw_value}.",
                retryable=True,
            )
        return int(raw_value)

    raise LLMProviderError(
        code=LLMErrorCode.PROVIDER_PROTOCOL_ERROR,
        provider=provider,
        message=f"Invalid usage field {field_name}: unsupported value type.",
        retryable=True,
    )


def _normalize_cost(value: float | None) -> Decimal:
    if value is None:
        return Decimal("0.0000")
    decimal_value = Decimal(str(value))
    if decimal_value < 0:
        return Decimal("0.0000")
    return decimal_value.quantize(_COST_SCALE, rounding=ROUND_HALF_UP)


def _map_assistant_error(*, provider: str, assistant_error: str) -> LLMProviderError:
    if assistant_error == "authentication_failed":
        return LLMProviderError(
            code=LLMErrorCode.AUTHENTICATION_FAILED,
            provider=provider,
            message="Claude authentication failed.",
            retryable=False,
        )
    if assistant_error == "rate_limit":
        return LLMProviderError(
            code=LLMErrorCode.RATE_LIMITED,
            provider=provider,
            message="Claude rate limit exceeded.",
            retryable=True,
        )
    if assistant_error == "invalid_request":
        return LLMProviderError(
            code=LLMErrorCode.INVALID_REQUEST,
            provider=provider,
            message="Claude rejected the request payload.",
            retryable=False,
        )
    if assistant_error == "server_error":
        return LLMProviderError(
            code=LLMErrorCode.PROVIDER_UNAVAILABLE,
            provider=provider,
            message="Claude provider reported server error.",
            retryable=True,
        )
    return LLMProviderError(
        code=LLMErrorCode.EXECUTION_FAILED,
        provider=provider,
        message=f"Claude assistant returned error: {assistant_error}.",
        retryable=True,
    )


def _map_result_error(*, provider: str, result: ResultMessage) -> LLMProviderError:
    subtype = result.subtype.strip().lower()
    message = result.result or f"Claude run failed with subtype {result.subtype}."

    if "max_turn" in subtype:
        return LLMProviderError(
            code=LLMErrorCode.CONTEXT_LIMIT_EXCEEDED,
            provider=provider,
            message=message,
            retryable=False,
        )
    if "interrupt" in subtype or "cancel" in subtype:
        return LLMProviderError(
            code=LLMErrorCode.CANCELLED,
            provider=provider,
            message=message,
            retryable=False,
        )

    return LLMProviderError(
        code=LLMErrorCode.EXECUTION_FAILED,
        provider=provider,
        message=message,
        retryable=True,
    )
