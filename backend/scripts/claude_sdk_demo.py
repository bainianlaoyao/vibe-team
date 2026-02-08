from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

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
from claude_agent_sdk.types import StreamEvent, ToolResultBlock


@dataclass(frozen=True, slots=True)
class AuthConfig:
    env: dict[str, str]
    summary: str
    settings_path: Path | None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Minimal Claude Agent SDK conversation demo.")
    parser.add_argument("--prompt", required=True, help="First user prompt.")
    parser.add_argument("--follow-up", default=None, help="Optional second turn prompt.")
    parser.add_argument(
        "--session-id",
        default=None,
        help="Conversation session_id. Randomly generated when omitted.",
    )
    parser.add_argument(
        "--system-prompt",
        default="You are a concise coding assistant.",
        help="System prompt passed to ClaudeAgentOptions.",
    )
    parser.add_argument("--model", default=None, help="Optional model override.")
    parser.add_argument("--max-turns", type=int, default=8, help="Maximum turn budget.")
    parser.add_argument(
        "--claude-settings-path",
        default=None,
        help=(
            "Optional Claude settings path. " "Defaults to ~/.claude/settings.json when available."
        ),
    )
    parser.add_argument(
        "--anthropic-api-key",
        default=None,
        help="API key passed to ANTHROPIC_API_KEY for the SDK subprocess.",
    )
    parser.add_argument(
        "--cli-path",
        default=None,
        help="Optional Claude CLI path override. Useful when forcing system-installed claude.",
    )
    parser.add_argument(
        "--permission-mode",
        choices=["default", "acceptEdits", "plan", "bypassPermissions"],
        default="default",
        help="Claude Code permission mode.",
    )
    parser.add_argument(
        "--cwd",
        default=".",
        help="Working directory provided to Claude Code.",
    )
    parser.add_argument(
        "--show-stream",
        action="store_true",
        help="Print text deltas from StreamEvent when available.",
    )
    parser.add_argument(
        "--interrupt-after-ms",
        type=int,
        default=0,
        help="Interrupt one turn after N milliseconds. 0 disables interrupt.",
    )
    parser.add_argument(
        "--allow-missing-auth",
        action="store_true",
        help="Run even when no API key or cloud provider auth env is found.",
    )
    return parser


def _extract_stream_text(event: dict[str, object]) -> str | None:
    event_type = event.get("type")
    if event_type == "content_block_delta":
        delta = event.get("delta")
        if isinstance(delta, dict):
            delta_type = delta.get("type")
            if delta_type == "text_delta":
                text = delta.get("text")
                if isinstance(text, str) and text:
                    return text
    if event_type == "text_delta":
        text = event.get("text")
        if isinstance(text, str) and text:
            return text
    return None


def _extract_assistant_text(message: AssistantMessage) -> str:
    parts: list[str] = []
    for block in message.content:
        if isinstance(block, TextBlock):
            parts.append(block.text)
    return "".join(parts).strip()


def _print_tool_summary(message: AssistantMessage) -> None:
    tool_uses = [block for block in message.content if isinstance(block, ToolUseBlock)]
    if not tool_uses:
        return
    for tool_use in tool_uses:
        input_json = json.dumps(tool_use.input, ensure_ascii=False)
        print(f"[tool_use] id={tool_use.id} name={tool_use.name} input={input_json}")

    tool_results = [block for block in message.content if isinstance(block, ToolResultBlock)]
    for result in tool_results:
        is_error = bool(result.is_error)
        print(f"[tool_result] tool_use_id={result.tool_use_id} is_error={is_error}")


def _print_result_usage(message: ResultMessage) -> None:
    print(
        "[result] "
        f"subtype={message.subtype} is_error={message.is_error} "
        f"duration_ms={message.duration_ms} duration_api_ms={message.duration_api_ms} "
        f"num_turns={message.num_turns} total_cost_usd={message.total_cost_usd}"
    )
    if message.usage:
        usage_json = json.dumps(message.usage, ensure_ascii=False)
        print(f"[usage] {usage_json}")


async def _schedule_interrupt(
    *,
    client: ClaudeSDKClient,
    interrupt_after_ms: int,
) -> None:
    await asyncio.sleep(interrupt_after_ms / 1000.0)
    await client.interrupt()
    print("\n[demo] interrupt signal sent.")


async def _run_turn(
    *,
    client: ClaudeSDKClient,
    prompt: str,
    session_id: str,
    show_stream: bool,
    interrupt_after_ms: int,
) -> None:
    print(f"\n[user] {prompt}")
    await client.query(prompt, session_id=session_id)

    interrupt_task: asyncio.Task[None] | None = None
    streamed_chunks = 0
    assistant_printed = False

    try:
        if interrupt_after_ms > 0:
            interrupt_task = asyncio.create_task(
                _schedule_interrupt(client=client, interrupt_after_ms=interrupt_after_ms)
            )

        async for message in client.receive_response():
            if isinstance(message, StreamEvent):
                if not show_stream:
                    continue
                chunk = _extract_stream_text(message.event)
                if chunk is None:
                    continue
                if streamed_chunks == 0:
                    print("[assistant.stream] ", end="", flush=True)
                print(chunk, end="", flush=True)
                streamed_chunks += 1
                continue

            if isinstance(message, AssistantMessage):
                if streamed_chunks > 0:
                    continue
                text = _extract_assistant_text(message)
                if text:
                    print(f"[assistant] {text}")
                    assistant_printed = True
                _print_tool_summary(message)
                continue

            if isinstance(message, ResultMessage):
                if streamed_chunks > 0:
                    print()
                if not assistant_printed and message.result:
                    print(f"[assistant.result] {message.result}")
                _print_result_usage(message)
    finally:
        if interrupt_task is not None:
            interrupt_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await interrupt_task


def _validate_args(args: argparse.Namespace) -> None:
    if args.max_turns is not None and args.max_turns <= 0:
        raise ValueError("--max-turns must be a positive integer.")
    if args.interrupt_after_ms < 0:
        raise ValueError("--interrupt-after-ms cannot be negative.")


def _resolve_settings_path(args: argparse.Namespace) -> Path | None:
    if isinstance(args.claude_settings_path, str) and args.claude_settings_path.strip():
        candidate = Path(args.claude_settings_path).expanduser().resolve()
        if candidate.exists() and candidate.is_file():
            return candidate
        return None

    default_path = Path.home() / ".claude" / "settings.json"
    if default_path.exists() and default_path.is_file():
        return default_path.resolve()
    return None


def _load_settings_env(settings_path: Path | None) -> dict[str, str]:
    if settings_path is None:
        return {}
    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(payload, dict):
        return {}
    raw_env = payload.get("env")
    if not isinstance(raw_env, dict):
        return {}

    env_map: dict[str, str] = {}
    for key, value in raw_env.items():
        if isinstance(key, str) and isinstance(value, str):
            env_map[key] = value
    return env_map


def _resolve_auth_config(args: argparse.Namespace) -> AuthConfig:
    settings_path = _resolve_settings_path(args)
    resolved_env = _load_settings_env(settings_path)

    explicit_key = (
        args.anthropic_api_key.strip()
        if isinstance(args.anthropic_api_key, str) and args.anthropic_api_key.strip()
        else None
    )

    shell_overrides: dict[str, str] = {}
    for env_name in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CODE_USE_FOUNDRY",
    ):
        env_value = os.getenv(env_name)
        if env_value:
            shell_overrides[env_name] = env_value

    legacy_key = os.getenv("CLAUDE_API_KEY")
    if legacy_key and "ANTHROPIC_API_KEY" not in shell_overrides:
        shell_overrides["ANTHROPIC_API_KEY"] = legacy_key

    resolved_env.update(shell_overrides)
    if explicit_key:
        resolved_env["ANTHROPIC_API_KEY"] = explicit_key

    summary_parts: list[str] = []
    if settings_path is not None:
        summary_parts.append(f"settings:{settings_path}")
    if shell_overrides:
        summary_parts.append("shell_env_overrides")
    if explicit_key:
        summary_parts.append("anthropic_api_key_arg")

    if not summary_parts:
        summary_parts.append("no authentication env detected")

    has_auth = any(
        key in resolved_env
        for key in (
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "CLAUDE_CODE_USE_BEDROCK",
            "CLAUDE_CODE_USE_VERTEX",
            "CLAUDE_CODE_USE_FOUNDRY",
        )
    )
    if not has_auth:
        summary_parts.append("auth_key_missing")

    return AuthConfig(
        env=resolved_env,
        summary=" + ".join(summary_parts),
        settings_path=settings_path,
    )


def _redact_env_preview(env: dict[str, str]) -> dict[str, str]:
    preview: dict[str, str] = {}
    for provider_env in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CODE_USE_FOUNDRY",
    ):
        if provider_env in env:
            preview[provider_env] = "***"
    return preview


def _build_options(args: argparse.Namespace, auth: AuthConfig) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=args.system_prompt,
        model=args.model,
        max_turns=args.max_turns,
        permission_mode=args.permission_mode,
        cwd=Path(args.cwd).resolve(),
        cli_path=args.cli_path,
        settings=str(auth.settings_path) if auth.settings_path else None,
        env=auth.env,
    )


def _ensure_auth_is_configured(*, auth: AuthConfig, allow_missing_auth: bool) -> None:
    if auth.env:
        return
    if allow_missing_auth:
        print("[demo] warning: missing auth env, continuing because --allow-missing-auth is set.")
        return
    raise ValueError(
        "No auth env found. Set ANTHROPIC_API_KEY (recommended), "
        "or set one of CLAUDE_CODE_USE_BEDROCK / CLAUDE_CODE_USE_VERTEX / "
        "CLAUDE_CODE_USE_FOUNDRY. "
        "For quick test: `set ANTHROPIC_API_KEY=...` (cmd) or "
        "`$env:ANTHROPIC_API_KEY='...'` (PowerShell)."
    )


async def _run(args: argparse.Namespace) -> int:
    _validate_args(args)
    auth = _resolve_auth_config(args)
    _ensure_auth_is_configured(auth=auth, allow_missing_auth=args.allow_missing_auth)

    session_id = args.session_id or f"demo-{uuid4().hex[:12]}"
    options = _build_options(args, auth)

    print(f"[demo] session_id={session_id}")
    print(f"[demo] cwd={Path(args.cwd).resolve()}")
    print(f"[demo] model={args.model or '(default)'}")
    print(f"[demo] auth={auth.summary}")
    print(f"[demo] cli_path={args.cli_path or '(sdk auto-detect)'}")
    print(f"[demo] auth_env_keys={json.dumps(_redact_env_preview(auth.env), ensure_ascii=False)}")

    prompts: list[str] = [args.prompt]
    if args.follow_up:
        prompts.append(args.follow_up)

    async with ClaudeSDKClient(options=options) as client:
        for index, prompt in enumerate(prompts, start=1):
            print(f"[demo] turn={index}/{len(prompts)}")
            await _run_turn(
                client=client,
                prompt=prompt,
                session_id=session_id,
                show_stream=args.show_stream,
                interrupt_after_ms=args.interrupt_after_ms if index == 1 else 0,
            )
    return 0


def _print_known_failures(exc: Exception) -> None:
    if isinstance(exc, ValueError):
        print(f"[demo] {exc}")
        return
    if isinstance(exc, CLINotFoundError):
        print("[demo] Claude CLI not found. Install Claude Code and retry.")
        return
    if isinstance(exc, CLIConnectionError):
        print(f"[demo] Failed to connect to Claude CLI: {exc}")
        return
    if isinstance(exc, CLIJSONDecodeError):
        print(f"[demo] Invalid CLI response payload: {exc}")
        return
    if isinstance(exc, ProcessError):
        print(f"[demo] Claude process error: {exc}")
        return
    if isinstance(exc, ClaudeSDKError):
        print(f"[demo] Claude SDK error: {exc}")
        return
    print(f"[demo] Unexpected error: {exc}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except Exception as exc:  # noqa: BLE001
        _print_known_failures(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
