"""
Windows-compatible Claude Code adapter using synchronous subprocess.

This adapter works around the Windows asyncio subprocess limitation
by running Claude CLI calls in a thread pool executor.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import subprocess
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from app.llm.contracts import (
    LLMClient,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMUsage,
    StreamCallback,
    StreamEvent,
    StreamEventType,
)
from app.llm.errors import LLMErrorCode, LLMProviderError
from app.llm.providers.claude_settings import resolve_claude_auth

CLAUDE_PROVIDER_NAME = "claude_code"
_COST_SCALE = Decimal("0.0001")

# Thread pool for running synchronous subprocess calls
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="claude-cli")


def _get_claude_cli_path(cli_path: str | Path | None = None) -> str:
    """Get the Claude CLI executable path."""
    if cli_path:
        return str(cli_path)

    # On Windows, we need to use claude.cmd
    if sys.platform == "win32":
        return "claude.cmd"
    return "claude"


def _sync_claude_call(
    *,
    prompt: str,
    model: str | None,
    system_prompt: str | None,
    max_turns: int | None,
    cwd: str | Path | None,
    cli_path: str,
    env: dict[str, str],
    session_id: str,
) -> dict[str, Any]:
    """
    Synchronous Claude CLI call using subprocess.

    This runs in a thread pool to avoid blocking the event loop.
    """
    cmd = [cli_path, "-p"]  # -p for print mode (non-interactive)

    if model:
        cmd.extend(["--model", model])

    if system_prompt:
        cmd.extend(["--system-prompt", system_prompt])

    if max_turns:
        cmd.extend(["--max-turns", str(max_turns)])

    cmd.extend(["--output-format", "json"])
    cmd.append(prompt)

    # Merge environment
    import os

    full_env = os.environ.copy()
    full_env.update(env)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            cwd=str(cwd) if cwd else None,
            env=full_env,
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "success": False,
            "error": "timeout",
            "message": f"Command timed out after {e.timeout}s",
        }
    except FileNotFoundError as e:
        return {
            "success": False,
            "error": "not_found",
            "message": f"Claude CLI not found: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "error": "unknown",
            "message": str(e),
        }


def _parse_claude_output(output: str) -> dict[str, Any]:
    """Parse Claude CLI JSON output."""
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        # If not JSON, treat as plain text response
        return {
            "result": output.strip(),
            "is_error": False,
        }


class ClaudeCodeSubprocessAdapter(LLMClient):
    """
    Claude Code adapter using synchronous subprocess calls.

    This adapter is designed for Windows compatibility where asyncio
    subprocess is not supported in uvicorn's default event loop.
    """

    def __init__(
        self,
        *,
        settings_path: str | Path | None = None,
        cli_path: str | Path | None = None,
        default_max_turns: int | None = None,
    ) -> None:
        self._settings_path = settings_path
        self._cli_path = _get_claude_cli_path(cli_path)
        self._default_max_turns = default_max_turns or 8

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate a response using Claude CLI."""
        prompt = _extract_last_user_prompt(request.messages)
        auth = resolve_claude_auth(settings_path_override=self._settings_path)

        loop = asyncio.get_running_loop()

        # Run synchronous subprocess in thread pool
        result = await loop.run_in_executor(
            _executor,
            lambda: _sync_claude_call(
                prompt=prompt,
                model=request.model,
                system_prompt=request.system_prompt,
                max_turns=request.max_turns or self._default_max_turns,
                cwd=request.cwd,
                cli_path=self._cli_path,
                env=auth.env,
                session_id=request.session_id,
            ),
        )

        if not result["success"]:
            error_type = result.get("error", "unknown")
            message = result.get("message", "Unknown error")

            if error_type == "not_found":
                raise LLMProviderError(
                    code=LLMErrorCode.PROVIDER_NOT_FOUND,
                    provider=request.provider,
                    message=message,
                    retryable=False,
                )
            elif error_type == "timeout":
                raise LLMProviderError(
                    code=LLMErrorCode.PROVIDER_UNAVAILABLE,
                    provider=request.provider,
                    message=message,
                    retryable=True,
                )
            else:
                # Check stderr for more info
                stderr = result.get("stderr", "")
                raise LLMProviderError(
                    code=LLMErrorCode.EXECUTION_FAILED,
                    provider=request.provider,
                    message=f"{message}. stderr: {stderr[:200]}" if stderr else message,
                    retryable=True,
                )

        # Parse output
        stdout = result.get("stdout", "")
        parsed = _parse_claude_output(stdout)

        text = parsed.get("result", stdout.strip())

        # Extract usage if available
        usage_data = parsed.get("usage", {})
        usage = LLMUsage(
            request_count=1,
            token_in=usage_data.get("input_tokens", 0),
            token_out=usage_data.get("output_tokens", 0),
            cost_usd=_normalize_cost(parsed.get("total_cost_usd")),
        )

        return LLMResponse(
            provider=request.provider,
            model=request.model,
            session_id=parsed.get("session_id", request.session_id),
            text=text,
            tool_calls=[],  # CLI mode doesn't return tool calls
            usage=usage,
            stop_reason=parsed.get("stop_reason", "end_turn"),
            raw_result=stdout,
        )

    async def generate_stream(
        self,
        request: LLMRequest,
        callback: StreamCallback,
    ) -> LLMResponse:
        """
        Generate response with streaming callbacks.

        Note: The subprocess adapter doesn't support true streaming,
        so we simulate it by sending the complete response as a single chunk.
        """
        # Get the full response first
        response = await self.generate(request)

        # Send the text as a single chunk
        if response.text:
            await callback(
                StreamEvent(
                    event_type=StreamEventType.TEXT_CHUNK,
                    content=response.text,
                )
            )

        # Send complete event
        await callback(
            StreamEvent(
                event_type=StreamEventType.COMPLETE,
                usage=response.usage,
            )
        )

        return response


def _extract_last_user_prompt(messages: list[LLMMessage]) -> str:
    """Extract the last user message from the conversation."""
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


def _normalize_cost(value: float | None) -> Decimal:
    """Normalize cost value to Decimal."""
    if value is None:
        return Decimal("0.0000")
    decimal_value = Decimal(str(value))
    if decimal_value < 0:
        return Decimal("0.0000")
    return decimal_value.quantize(_COST_SCALE, rounding=ROUND_HALF_UP)
