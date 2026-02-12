# mypy: disable-error-code="no-untyped-def,call-arg"

import asyncio
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    CLIConnectionError,
    CLINotFoundError,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

from app.llm.contracts import LLMMessage, LLMRequest, LLMRole, LLMToolCall
from app.llm.errors import LLMErrorCode, LLMProviderError
from app.llm.providers.claude_code import (
    CLAUDE_PROVIDER_NAME,
    ClaudeCodeAdapter,
    _extract_last_user_prompt,
    _extract_usage,
    _normalize_cost,
)


# Mock classes for SDK interactions
class AsyncMockContextManager:
    def __init__(self, mock_client):
        self.mock_client = mock_client

    async def __aenter__(self):
        return self.mock_client

    async def __aexit__(self, exc_type, exc, tb):
        _ = (exc_type, exc, tb)
        return None


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.query = AsyncMock()
    client.receive_response = MagicMock()
    return client


@pytest.fixture
def adapter(mock_client):
    def factory(_options):
        return AsyncMockContextManager(mock_client)

    return ClaudeCodeAdapter(client_factory=factory)


@pytest.fixture
def sample_request():
    return LLMRequest(
        provider=CLAUDE_PROVIDER_NAME,
        model="claude-3-5-sonnet-20241022",
        messages=[LLMMessage(role=LLMRole.USER, content="Hello")],
        session_id="test-session",
    )


def test_generate_success(adapter, mock_client, sample_request):
    async def run_test() -> None:
        async def mock_stream():
            yield AssistantMessage(
                content=[TextBlock(text="Hello world")],
                model="claude-sonnet-4-5",
            )
            yield AssistantMessage(
                content=[ToolUseBlock(id="call_1", name="test_tool", input={"arg": 1})],
                model="claude-sonnet-4-5",
            )
            yield ResultMessage(
                subtype="completed",
                duration_ms=20,
                duration_api_ms=10,
                is_error=False,
                num_turns=1,
                session_id="new-session",
                result="Success",
                usage={"input_tokens": 10, "output_tokens": 5},
                total_cost_usd=0.00123,
            )

        mock_client.receive_response.return_value.__aiter__.side_effect = mock_stream

        with patch("app.llm.providers.claude_code.resolve_claude_auth") as mock_auth:
            mock_auth.return_value = MagicMock(settings_path=None, env={})
            response = await adapter.generate(sample_request)

        assert response.text == "Hello world"
        assert response.session_id == "new-session"
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0] == LLMToolCall(
            id="call_1",
            name="test_tool",
            arguments={"arg": 1},
        )
        assert response.usage.token_in == 10
        assert response.usage.token_out == 5
        assert response.usage.cost_usd == Decimal("0.0012")  # Quantized

    asyncio.run(run_test())


def test_generate_cli_not_found(adapter, sample_request):
    def factory_fail(_options):
        raise CLINotFoundError("CLI not found")

    adapter._client_factory = factory_fail

    async def run_test() -> None:
        with patch("app.llm.providers.claude_code.resolve_claude_auth"):
            with pytest.raises(LLMProviderError) as exc:
                await adapter.generate(sample_request)
            assert exc.value.code == LLMErrorCode.PROVIDER_NOT_FOUND
            assert not exc.value.retryable

    asyncio.run(run_test())


def test_generate_connection_error(adapter, sample_request):
    def factory_fail(_options):
        raise CLIConnectionError("Connection failed")

    adapter._client_factory = factory_fail

    async def run_test() -> None:
        with patch("app.llm.providers.claude_code.resolve_claude_auth"):
            with pytest.raises(LLMProviderError) as exc:
                await adapter.generate(sample_request)
            assert exc.value.code == LLMErrorCode.PROVIDER_UNAVAILABLE
            assert exc.value.retryable

    asyncio.run(run_test())


def test_protocol_error_no_result(adapter, mock_client, sample_request):
    async def run_test() -> None:
        async def empty_stream():
            if False:
                yield AssistantMessage(
                    content=[TextBlock(text="never")],
                    model="claude-sonnet-4-5",
                )

        mock_client.receive_response.return_value.__aiter__.side_effect = empty_stream

        with patch("app.llm.providers.claude_code.resolve_claude_auth"):
            with pytest.raises(LLMProviderError) as exc:
                await adapter.generate(sample_request)
            assert exc.value.code == LLMErrorCode.PROVIDER_PROTOCOL_ERROR
            assert "without ResultMessage" in exc.value.message

    asyncio.run(run_test())


def test_generate_uses_windows_default_cli_path_when_not_configured(monkeypatch):
    captured: dict[str, Any] = {}
    client = MagicMock()
    client.query = AsyncMock()
    client.receive_response = MagicMock()

    async def mock_stream():
        yield AssistantMessage(
            content=[TextBlock(text="ok")],
            model="claude-sonnet-4-5",
        )
        yield ResultMessage(
            subtype="completed",
            duration_ms=15,
            duration_api_ms=10,
            is_error=False,
            num_turns=1,
            session_id="session-1",
            result="ok",
            usage={"input_tokens": 1, "output_tokens": 1},
            total_cost_usd=0.0001,
        )

    client.receive_response.return_value.__aiter__.side_effect = mock_stream

    def factory(options):
        captured["cli_path"] = options.cli_path
        return AsyncMockContextManager(client)

    monkeypatch.setattr("app.llm.providers.claude_settings.sys.platform", "win32")
    adapter = ClaudeCodeAdapter(client_factory=factory)
    request = LLMRequest(
        provider=CLAUDE_PROVIDER_NAME,
        model="claude-sonnet-4-5",
        messages=[LLMMessage(role=LLMRole.USER, content="Hello")],
        session_id="test-session",
    )

    async def run_test() -> None:
        with patch("app.llm.providers.claude_code.resolve_claude_auth") as mock_auth:
            mock_auth.return_value = MagicMock(settings_path=None, env={})
            await adapter.generate(request)

    asyncio.run(run_test())
    assert captured["cli_path"] == "claude.cmd"


def test_extract_last_user_prompt():
    messages = [
        LLMMessage(role=LLMRole.SYSTEM, content="sys"),
        LLMMessage(role=LLMRole.USER, content="  first user  "),
        LLMMessage(role=LLMRole.ASSISTANT, content="thinking"),
        LLMMessage(role=LLMRole.USER, content="  last user  "),
    ]
    assert _extract_last_user_prompt(messages) == "last user"

    with pytest.raises(LLMProviderError) as exc:
        _extract_last_user_prompt([LLMMessage(role=LLMRole.ASSISTANT, content="hi")])
    assert exc.value.code == LLMErrorCode.INVALID_REQUEST


def test_extract_usage_logic():
    result = ResultMessage(
        subtype="test",
        duration_ms=5,
        duration_api_ms=3,
        is_error=False,
        num_turns=1,
        session_id="usage-session",
        usage={
            "input_tokens": 100,
            "cache_creation_input_tokens": 50,
            "cache_read_input_tokens": 25,
            "output_tokens": 10,
        },
        total_cost_usd=0.005,
    )
    usage = _extract_usage(provider="test", result=result)
    assert usage.token_in == 175
    assert usage.token_out == 10
    assert usage.cost_usd == Decimal("0.0050")


def test_normalize_cost():
    assert _normalize_cost(None) == Decimal("0.0000")
    assert _normalize_cost(0.000123) == Decimal("0.0001")
    assert _normalize_cost(0.000156) == Decimal("0.0002")
    assert _normalize_cost(-1.0) == Decimal("0.0000")
