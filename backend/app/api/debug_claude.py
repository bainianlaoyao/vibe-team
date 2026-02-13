"""
Debug endpoint to test Claude SDK within uvicorn context.
Access via: GET http://127.0.0.1:8000/debug/claude-test
"""

from __future__ import annotations

import asyncio
import os
import shutil
import traceback
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter

from app.core.config import get_settings
from app.llm.contracts import LLMMessage, LLMRequest, LLMRole, StreamEvent, StreamingLLMClient
from app.llm.factory import create_llm_client
from app.llm.providers.claude_code import ClaudeCodeAdapter
from app.llm.providers.claude_settings import resolve_claude_auth, resolve_claude_permission_mode

router = APIRouter(prefix="/debug", tags=["debug_claude"])


@router.get("/claude-test")
async def test_claude_in_uvicorn() -> dict[str, Any]:
    """Test Claude SDK within uvicorn context."""
    results: dict[str, Any] = {}

    # Test 1: Environment
    results["environment"] = {
        "claude_path": shutil.which("claude"),
        "claude_cmd_path": shutil.which("claude.cmd"),
        "anthropic_base_url": os.environ.get("ANTHROPIC_BASE_URL", "<not set>"),
        "cwd": os.getcwd(),
    }

    # Test 2: Auth resolution
    try:
        auth = resolve_claude_auth()
        results["auth"] = {
            "settings_path": str(auth.settings_path) if auth.settings_path else None,
            "env_keys": list(auth.env.keys()),
        }
    except Exception as e:
        results["auth"] = {"error": f"{type(e).__name__}: {e}"}

    # Test 3: Subprocess claude.cmd
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude.cmd",
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        results["subprocess_claude_cmd"] = {
            "returncode": proc.returncode,
            "stdout": stdout.decode().strip(),
            "stderr": stderr.decode().strip(),
        }
    except Exception as e:
        results["subprocess_claude_cmd"] = {"error": f"{type(e).__name__}: {e}"}

    # Test 4: Claude SDK client creation
    try:
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

        options = ClaudeAgentOptions(
            model="claude-sonnet-4-20250514",
            cwd=str(Path.home()),
            max_turns=1,
            permission_mode=resolve_claude_permission_mode(),
        )
        async with ClaudeSDKClient(options=options) as client:
            results["sdk_client_creation"] = {"success": True, "client_type": str(type(client))}
    except Exception as e:
        results["sdk_client_creation"] = {
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
        }

    # Test 5: Claude SDK query
    try:
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage

        options = ClaudeAgentOptions(
            model="claude-sonnet-4-20250514",
            cwd=str(Path.home()),
            max_turns=1,
            permission_mode=resolve_claude_permission_mode(),
        )
        async with ClaudeSDKClient(options=options) as client:
            await client.query("Say 'uvicorn test OK'", session_id="uvicorn-debug")
            messages = []
            async for message in client.receive_response():
                messages.append(type(message).__name__)
                if isinstance(message, ResultMessage):
                    results["sdk_query"] = {
                        "success": True,
                        "messages": messages,
                        "result": message.result,
                        "is_error": message.is_error,
                    }
                    break
            else:
                results["sdk_query"] = {
                    "success": False,
                    "messages": messages,
                    "error": "No ResultMessage",
                }
    except Exception as e:
        results["sdk_query"] = {
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
        }

    # Test 6: ClaudeCodeAdapter
    try:
        adapter = ClaudeCodeAdapter()
        request = LLMRequest(
            provider="claude_code",
            model="claude-sonnet-4-5",
            messages=[LLMMessage(role=LLMRole.USER, content="Say 'adapter test OK'")],
            session_id="uvicorn-adapter-debug",
            system_prompt="Be very brief.",
            max_turns=1,
            cwd=Path.home(),
        )
        response = await adapter.generate(request)
        results["adapter"] = {
            "success": True,
            "text": response.text[:100] if response.text else None,
        }
    except Exception as e:
        results["adapter"] = {
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
        }

    # Test 7: Factory-created client (like WebSocket handler)
    try:
        settings = get_settings()
        llm_client = create_llm_client(provider="claude_code", settings=settings)
        request = LLMRequest(
            provider="claude_code",
            model="claude-sonnet-4-5",
            messages=[LLMMessage(role=LLMRole.USER, content="Say 'factory test OK'")],
            session_id="uvicorn-factory-debug",
            system_prompt="Be very brief.",
            max_turns=1,
            cwd=Path("E:/beebeebrain/play_ground"),
        )
        response = await llm_client.generate(request)
        results["factory_client"] = {
            "success": True,
            "text": response.text[:100] if response.text else None,
        }
    except Exception as e:
        results["factory_client"] = {
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
        }

    # Test 8: Streaming (like conversation executor)
    try:
        settings = get_settings()
        llm_client = create_llm_client(provider="claude_code", settings=settings)
        events: list[str] = []

        async def callback(event: StreamEvent) -> None:
            events.append(event.event_type.value)

        request = LLMRequest(
            provider="claude_code",
            model="claude-sonnet-4-5",
            messages=[LLMMessage(role=LLMRole.USER, content="Say 'stream test OK'")],
            session_id="uvicorn-stream-debug",
            system_prompt="Be very brief.",
            max_turns=1,
            cwd=Path("E:/beebeebrain/play_ground"),
        )
        streaming_client = cast(StreamingLLMClient, llm_client)
        response = await streaming_client.generate_stream(request, callback)
        results["streaming"] = {
            "success": True,
            "text": response.text[:100] if response.text else None,
            "events": events,
        }
    except Exception as e:
        results["streaming"] = {
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
        }

    return results
