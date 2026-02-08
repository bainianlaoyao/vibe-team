"""
Debug script to diagnose "Failed to start Claude Code" error.
Run with: uv run python scripts/debug_claude_sdk.py
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


def test_1_environment() -> None:
    """Test 1: Check environment variables and paths."""
    print_section("Test 1: Environment Check")

    # Check Claude CLI
    claude_path = shutil.which("claude")
    print(f"Claude CLI path: {claude_path}")

    claude_cmd_path = shutil.which("claude.cmd")
    print(f"Claude.cmd path: {claude_cmd_path}")

    # Check key environment variables
    env_vars = [
        "PATH",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "HOME",
        "USERPROFILE",
    ]

    for var in env_vars:
        value = os.environ.get(var, "<not set>")
        if var == "PATH":
            # Show first 200 chars of PATH
            print(f"{var}: {value[:200]}...")
        elif "KEY" in var or "TOKEN" in var:
            # Mask sensitive values
            print(f"{var}: {'*' * 10 if value != '<not set>' else value}")
        else:
            print(f"{var}: {value}")

    # Check settings file
    settings_path = Path.home() / ".claude" / "settings.json"
    print(f"\nSettings file exists: {settings_path.exists()}")
    if settings_path.exists():
        try:
            content = json.loads(settings_path.read_text())
            print(f"Settings content: {json.dumps(content, indent=2)}")
        except Exception as e:
            print(f"Error reading settings: {e}")


def test_2_subprocess_sync() -> None:
    """Test 2: Test Claude CLI via synchronous subprocess."""
    print_section("Test 2: Subprocess (sync)")

    commands = [
        (["claude", "--version"], "claude --version"),
        (["claude.cmd", "--version"], "claude.cmd --version"),
    ]

    for cmd, desc in commands:
        print(f"\nTesting: {desc}")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(Path.home()),
            )
            print(f"  Return code: {result.returncode}")
            print(f"  Stdout: {result.stdout.strip()}")
            print(f"  Stderr: {result.stderr.strip()}")
        except FileNotFoundError as e:
            print(f"  FileNotFoundError: {e}")
        except Exception as e:
            print(f"  Error: {type(e).__name__}: {e}")


async def test_3_subprocess_async() -> None:
    """Test 3: Test Claude CLI via asyncio subprocess."""
    print_section("Test 3: Subprocess (async)")

    commands = [
        (["claude", "--version"], "claude --version"),
        (["claude.cmd", "--version"], "claude.cmd --version"),
    ]

    for cmd, desc in commands:
        print(f"\nTesting: {desc}")
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(Path.home()),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            print(f"  Return code: {proc.returncode}")
            print(f"  Stdout: {stdout.decode().strip()}")
            print(f"  Stderr: {stderr.decode().strip()}")
        except FileNotFoundError as e:
            print(f"  FileNotFoundError: {e}")
        except Exception as e:
            print(f"  Error: {type(e).__name__}: {e}")


async def test_4_claude_sdk_basic() -> None:
    """Test 4: Test Claude SDK basic connection."""
    print_section("Test 4: Claude SDK Basic Connection")

    try:
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

        options = ClaudeAgentOptions(
            model="claude-sonnet-4-20250514",
            cwd=str(Path.home()),
        )
        print(f"Options created: model={options.model}, cwd={options.cwd}")

        print("Attempting to create client...")
        async with ClaudeSDKClient(options=options) as client:
            print("  Client created successfully!")
            print(f"  Client type: {type(client)}")

    except Exception as e:
        print(f"  Error: {type(e).__name__}: {e}")
        traceback.print_exc()


async def test_5_claude_sdk_with_query() -> None:
    """Test 5: Test Claude SDK with actual query."""
    print_section("Test 5: Claude SDK Query")

    try:
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

        options = ClaudeAgentOptions(
            model="claude-sonnet-4-20250514",
            cwd=str(Path.home()),
            max_turns=1,
        )

        print("Creating client and sending query...")
        async with ClaudeSDKClient(options=options) as client:
            await client.query("Say 'Hello World' and nothing else.", session_id="debug-test")

            message_count = 0
            async for message in client.receive_response():
                message_count += 1
                msg_type = type(message).__name__
                print(f"  Message {message_count}: {msg_type}")

                if hasattr(message, "content"):
                    content = getattr(message, "content", None)
                    if content:
                        print(f"    Content preview: {str(content)[:100]}...")

                if hasattr(message, "result"):
                    print(f"    Result: {getattr(message, 'result', None)}")

                if hasattr(message, "is_error"):
                    print(f"    Is error: {getattr(message, 'is_error', None)}")

                if message_count >= 5:
                    print("  (stopping after 5 messages)")
                    break

    except Exception as e:
        print(f"  Error: {type(e).__name__}: {e}")
        traceback.print_exc()


async def test_6_claude_adapter() -> None:
    """Test 6: Test ClaudeCodeAdapter from the backend."""
    print_section("Test 6: ClaudeCodeAdapter")

    try:
        from app.llm.contracts import LLMMessage, LLMRequest, LLMRole
        from app.llm.providers.claude_code import ClaudeCodeAdapter
        from app.llm.providers.claude_settings import resolve_claude_auth

        # Check auth
        auth = resolve_claude_auth()
        print(f"Auth settings path: {auth.settings_path}")
        print(f"Auth env: {auth.env}")

        # Create adapter
        adapter = ClaudeCodeAdapter()
        print("Adapter created")

        # Create request
        request = LLMRequest(
            provider="claude_code",
            model="claude-sonnet-4-5",
            messages=[LLMMessage(role=LLMRole.USER, content="Say hello")],
            session_id="debug-adapter-test",
            system_prompt="You are a helpful assistant. Be very brief.",
            max_turns=1,
            cwd=str(Path.home()),
        )
        print(f"Request created: model={request.model}, cwd={request.cwd}")

        # Execute
        print("Executing generate()...")
        response = await adapter.generate(request)
        print("  Response received!")
        print(f"  Text: {response.text[:100]}...")
        print(f"  Usage: {response.usage}")

    except Exception as e:
        print(f"  Error: {type(e).__name__}: {e}")
        traceback.print_exc()


async def test_7_simulate_ws_context() -> None:
    """Test 7: Simulate WebSocket conversation context."""
    print_section("Test 7: Simulated WebSocket Context")

    try:
        from app.core.config import get_settings
        from app.llm.contracts import LLMMessage, LLMRequest, LLMRole
        from app.llm.factory import create_llm_client

        settings = get_settings()
        print(f"Settings loaded: claude_cli_path={settings.claude_cli_path}")
        print(f"  claude_settings_path={settings.claude_settings_path}")
        print(f"  claude_default_max_turns={settings.claude_default_max_turns}")

        # Create client like ws_conversations.py does
        llm_client = create_llm_client(provider="claude_code", settings=settings)
        print(f"LLM client created: {type(llm_client)}")

        # Create request like conversation_executor.py does
        request = LLMRequest(
            provider="claude_code",
            model="claude-sonnet-4-5",
            messages=[LLMMessage(role=LLMRole.USER, content="Hello test")],
            session_id="debug-ws-test",
            system_prompt="You are a helpful assistant.",
            max_turns=8,
            cwd="E:/beebeebrain/play_ground",
        )

        print("Executing generate()...")
        response = await llm_client.generate(request)
        print(f"  Response: {response.text[:100]}...")

    except Exception as e:
        print(f"  Error: {type(e).__name__}: {e}")
        traceback.print_exc()


async def test_8_stream_callback() -> None:
    """Test 8: Test streaming with callback (like conversation executor)."""
    print_section("Test 8: Streaming with Callback")

    try:
        from app.core.config import get_settings
        from app.llm.contracts import LLMMessage, LLMRequest, LLMRole, StreamEvent
        from app.llm.factory import create_llm_client

        settings = get_settings()
        llm_client = create_llm_client(provider="claude_code", settings=settings)

        events_received: list[str] = []

        async def callback(event: StreamEvent) -> None:
            events_received.append(event.event_type.value)
            print(f"  Event: {event.event_type.value}")
            if event.content:
                print(f"    Content: {event.content[:50]}...")
            if event.error:
                print(f"    Error: {event.error}")

        request = LLMRequest(
            provider="claude_code",
            model="claude-sonnet-4-5",
            messages=[LLMMessage(role=LLMRole.USER, content="Say hello briefly")],
            session_id="debug-stream-test",
            system_prompt="Be very brief.",
            max_turns=1,
            cwd="E:/beebeebrain/play_ground",
        )

        print("Executing generate_stream()...")
        response = await llm_client.generate_stream(request, callback)
        print(f"  Final response: {response.text[:100]}...")
        print(f"  Events received: {events_received}")

    except Exception as e:
        print(f"  Error: {type(e).__name__}: {e}")
        traceback.print_exc()


async def test_9_concurrent_clients() -> None:
    """Test 9: Test if concurrent clients cause issues."""
    print_section("Test 9: Concurrent Clients")

    try:
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

        async def run_client(client_id: int) -> str:
            options = ClaudeAgentOptions(
                model="claude-sonnet-4-20250514",
                cwd=str(Path.home()),
                max_turns=1,
            )
            try:
                async with ClaudeSDKClient(options=options) as client:
                    await client.query(
                        f"Say 'Client {client_id} OK'", session_id=f"concurrent-{client_id}"
                    )
                    async for message in client.receive_response():
                        if hasattr(message, "result") and message.result:
                            return f"Client {client_id}: OK"
                return f"Client {client_id}: No result"
            except Exception as e:
                return f"Client {client_id}: Error - {type(e).__name__}: {e}"

        # Run 2 clients concurrently
        print("Running 2 clients concurrently...")
        results = await asyncio.gather(run_client(1), run_client(2), return_exceptions=True)

        for i, result in enumerate(results):
            print(f"  Result {i + 1}: {result}")

    except Exception as e:
        print(f"  Error: {type(e).__name__}: {e}")
        traceback.print_exc()


async def test_10_check_running_processes() -> None:
    """Test 10: Check for running Claude processes."""
    print_section("Test 10: Running Claude Processes")

    try:
        # Windows-specific: check for claude processes
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq claude*"],
            capture_output=True,
            text=True,
        )
        print(f"Claude processes:\n{result.stdout}")

        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq node*"],
            capture_output=True,
            text=True,
        )
        lines = result.stdout.strip().split("\n")
        node_count = len([line for line in lines if "node" in line.lower()])
        print(f"Node.js processes: {node_count} running")

    except Exception as e:
        print(f"  Error: {type(e).__name__}: {e}")


async def main() -> None:
    print("\n" + "=" * 60)
    print("  Claude SDK Debug Script")
    print("=" * 60)
    print(f"Python: {sys.executable}")
    print(f"CWD: {os.getcwd()}")
    print(f"Platform: {sys.platform}")

    # Run all tests
    test_1_environment()
    test_2_subprocess_sync()
    await test_3_subprocess_async()
    await test_4_claude_sdk_basic()
    await test_5_claude_sdk_with_query()
    await test_6_claude_adapter()
    await test_7_simulate_ws_context()
    await test_8_stream_callback()
    await test_9_concurrent_clients()
    await test_10_check_running_processes()

    print_section("All Tests Completed")


if __name__ == "__main__":
    asyncio.run(main())
