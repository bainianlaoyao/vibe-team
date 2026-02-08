from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk import CLIConnectionError, CLIJSONDecodeError, CLINotFoundError, ProcessError
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

from app.llm.contracts import LLMMessage, LLMRequest, LLMRole
from app.llm.errors import LLMErrorCode, LLMProviderError
from app.llm.providers.claude_code import ClaudeCodeAdapter


class FakeClaudeClient:
    def __init__(self, *, messages: list[Any]) -> None:
        self._messages = messages
        self.queries: list[tuple[str, str]] = []

    async def __aenter__(self) -> FakeClaudeClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> bool:
        return False

    async def query(self, prompt: str, session_id: str = "default") -> None:
        self.queries.append((prompt, session_id))

    def receive_response(self) -> Any:
        async def _iter() -> Any:
            for message in self._messages:
                yield message

        return _iter()


class FailingContextManager:
    def __init__(self, *, error: Exception) -> None:
        self._error = error

    async def __aenter__(self) -> Any:
        raise self._error

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> bool:
        return False


def _request(messages: list[LLMMessage] | None = None) -> LLMRequest:
    return LLMRequest(
        provider="claude_code",
        model="claude-sonnet-4-5",
        messages=messages or [LLMMessage(role=LLMRole.USER, content="hello")],
        session_id="demo-session",
        system_prompt="You are concise.",
    )


def _result_message(
    *,
    is_error: bool = False,
    subtype: str = "success",
    usage: dict[str, Any] | None = None,
    result: str | None = None,
) -> ResultMessage:
    return ResultMessage(
        subtype=subtype,
        duration_ms=42,
        duration_api_ms=40,
        is_error=is_error,
        num_turns=1,
        session_id="demo-session",
        total_cost_usd=0.01236,
        usage=usage
        or {
            "input_tokens": 120,
            "cache_creation_input_tokens": 40,
            "cache_read_input_tokens": 20,
            "output_tokens": 55,
        },
        result=result,
    )


def _set_fake_home(monkeypatch: pytest.MonkeyPatch, *, home_path: Path) -> None:
    monkeypatch.setenv("HOME", str(home_path))
    monkeypatch.setenv("USERPROFILE", str(home_path))


def test_claude_adapter_uses_user_settings_for_auth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_path = settings_dir / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "env": {
                    "ANTHROPIC_AUTH_TOKEN": "token-from-settings",
                    "ANTHROPIC_BASE_URL": "https://example.invalid",
                }
            }
        ),
        encoding="utf-8",
    )
    _set_fake_home(monkeypatch, home_path=tmp_path)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    captured_options: list[Any] = []

    def client_factory(options: Any) -> FakeClaudeClient:
        captured_options.append(options)
        return FakeClaudeClient(
            messages=[
                AssistantMessage(
                    content=[
                        TextBlock(text="hello world"),
                        ToolUseBlock(id="tool-1", name="read_file", input={"path": "README.md"}),
                    ],
                    model="claude-sonnet-4-5",
                ),
                _result_message(),
            ]
        )

    adapter = ClaudeCodeAdapter(client_factory=client_factory)
    response = asyncio.run(adapter.generate(_request()))

    assert response.text == "hello world"
    assert response.tool_calls[0].name == "read_file"
    assert response.usage.token_in == 180
    assert response.usage.token_out == 55
    assert str(response.usage.cost_usd) == "0.0124"
    assert captured_options
    assert captured_options[0].settings == str(settings_path.resolve())
    assert captured_options[0].env["ANTHROPIC_AUTH_TOKEN"] == "token-from-settings"


@pytest.mark.parametrize(
    ("error", "expected_code", "expected_retryable"),
    [
        (CLINotFoundError("missing"), LLMErrorCode.PROVIDER_NOT_FOUND, False),
        (CLIConnectionError("down"), LLMErrorCode.PROVIDER_UNAVAILABLE, True),
        (
            CLIJSONDecodeError("bad payload", ValueError("malformed")),
            LLMErrorCode.PROVIDER_PROTOCOL_ERROR,
            True,
        ),
        (
            ProcessError("exit 1", exit_code=1, stderr="failed"),
            LLMErrorCode.EXECUTION_FAILED,
            True,
        ),
    ],
)
def test_claude_adapter_maps_provider_exceptions(
    error: Exception,
    expected_code: LLMErrorCode,
    expected_retryable: bool,
) -> None:
    adapter = ClaudeCodeAdapter(client_factory=lambda _: FailingContextManager(error=error))

    with pytest.raises(LLMProviderError) as exc_info:
        asyncio.run(adapter.generate(_request()))

    assert exc_info.value.code == expected_code
    assert exc_info.value.retryable is expected_retryable


def test_claude_adapter_maps_assistant_rate_limit_to_standard_error() -> None:
    adapter = ClaudeCodeAdapter(
        client_factory=lambda _: FakeClaudeClient(
            messages=[
                AssistantMessage(content=[], model="claude-sonnet-4-5", error="rate_limit"),
                _result_message(),
            ]
        )
    )

    with pytest.raises(LLMProviderError) as exc_info:
        asyncio.run(adapter.generate(_request()))

    assert exc_info.value.code == LLMErrorCode.RATE_LIMITED
    assert exc_info.value.retryable is True


def test_claude_adapter_rejects_malformed_usage_payload() -> None:
    adapter = ClaudeCodeAdapter(
        client_factory=lambda _: FakeClaudeClient(
            messages=[
                AssistantMessage(content=[TextBlock(text="ok")], model="claude-sonnet-4-5"),
                _result_message(usage={"input_tokens": "bad", "output_tokens": 1}),
            ]
        )
    )

    with pytest.raises(LLMProviderError) as exc_info:
        asyncio.run(adapter.generate(_request()))

    assert exc_info.value.code == LLMErrorCode.PROVIDER_PROTOCOL_ERROR


def test_claude_adapter_maps_context_limit_error() -> None:
    adapter = ClaudeCodeAdapter(
        client_factory=lambda _: FakeClaudeClient(
            messages=[
                AssistantMessage(content=[TextBlock(text="partial")], model="claude-sonnet-4-5"),
                _result_message(
                    is_error=True,
                    subtype="error_max_turns",
                    result="max turns reached",
                ),
            ]
        )
    )

    with pytest.raises(LLMProviderError) as exc_info:
        asyncio.run(adapter.generate(_request()))

    assert exc_info.value.code == LLMErrorCode.CONTEXT_LIMIT_EXCEEDED
    assert exc_info.value.retryable is False


def test_claude_adapter_requires_user_prompt() -> None:
    adapter = ClaudeCodeAdapter(client_factory=lambda _: FakeClaudeClient(messages=[]))
    request = _request(messages=[LLMMessage(role=LLMRole.SYSTEM, content="no user prompt")])

    with pytest.raises(LLMProviderError) as exc_info:
        asyncio.run(adapter.generate(request))

    assert exc_info.value.code == LLMErrorCode.INVALID_REQUEST
