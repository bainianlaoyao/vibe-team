"""
Test script to evaluate two solutions for Windows asyncio subprocess issue.

Solution 1: WindowsProactorEventLoopPolicy
Solution 2: run_in_executor wrapper

Run with: uv run python scripts/test_event_loop_solutions.py
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def print_section(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print("=" * 70)


async def test_asyncio_subprocess() -> dict[str, Any]:
    """Test if asyncio subprocess works in current event loop."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude.cmd",
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        return {
            "success": True,
            "returncode": proc.returncode,
            "stdout": stdout.decode().strip(),
        }
    except NotImplementedError:
        return {"success": False, "error": "NotImplementedError - subprocess not supported"}
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


async def test_claude_sdk() -> dict[str, Any]:
    """Test Claude SDK in current event loop."""
    try:
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage

        options = ClaudeAgentOptions(
            model="claude-sonnet-4-20250514",
            cwd=str(Path.home()),
            max_turns=1,
        )
        async with ClaudeSDKClient(options=options) as client:
            await client.query("Say 'test OK'", session_id="loop-test")
            async for message in client.receive_response():
                if isinstance(message, ResultMessage):
                    return {"success": True, "result": message.result}
        return {"success": False, "error": "No result message"}
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


# =============================================================================
# Solution 1: WindowsProactorEventLoopPolicy
# =============================================================================


def solution1_set_policy() -> None:
    """Set Windows Proactor event loop policy."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


async def test_solution1() -> dict[str, Any]:
    """Test Solution 1: WindowsProactorEventLoopPolicy."""
    results: dict[str, Any] = {}

    # Test subprocess
    results["subprocess"] = await test_asyncio_subprocess()

    # Test Claude SDK
    results["claude_sdk"] = await test_claude_sdk()

    return results


# =============================================================================
# Solution 2: run_in_executor wrapper
# =============================================================================


def sync_claude_query(prompt: str) -> dict[str, Any]:
    """Synchronous wrapper for Claude CLI call using subprocess."""
    try:
        # Use synchronous subprocess instead of asyncio
        result = subprocess.run(
            [
                "claude.cmd",
                "-p",  # print mode
                "--max-turns",
                "1",
                "--output-format",
                "text",
                prompt,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(Path.home()),
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:200] if result.stdout else None,
            "stderr": result.stderr[:200] if result.stderr else None,
            "returncode": result.returncode,
        }
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


async def test_solution2_executor() -> dict[str, Any]:
    """Test Solution 2: run_in_executor with synchronous subprocess."""
    results: dict[str, Any] = {}

    # Test with ThreadPoolExecutor
    loop = asyncio.get_running_loop()

    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        # Single call
        future = loop.run_in_executor(executor, sync_claude_query, "Say 'executor test OK'")
        result = await future
        results["single_call"] = result
        results["single_call_time"] = time.time() - start

        # Concurrent calls
        start = time.time()
        futures = [
            loop.run_in_executor(executor, sync_claude_query, f"Say 'concurrent {i}'")
            for i in range(2)
        ]
        concurrent_results = await asyncio.gather(*futures, return_exceptions=True)
        results["concurrent_calls"] = [
            r if isinstance(r, dict) else {"error": str(r)} for r in concurrent_results
        ]
        results["concurrent_time"] = time.time() - start

    return results


# =============================================================================
# Simulated uvicorn environment tests
# =============================================================================


def simulate_uvicorn_default_loop() -> dict[str, Any]:
    """Simulate uvicorn's default event loop (Selector on Windows)."""
    print("\n--- Simulating uvicorn default loop (SelectorEventLoop) ---")

    if sys.platform == "win32":
        # uvicorn uses SelectorEventLoop by default on Windows
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(test_asyncio_subprocess())
        return result
    finally:
        loop.close()


def simulate_uvicorn_proactor_loop() -> dict[str, Any]:
    """Simulate uvicorn with Proactor loop."""
    print("\n--- Simulating uvicorn with ProactorEventLoop ---")

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(test_asyncio_subprocess())
        return result
    finally:
        loop.close()


def test_executor_in_selector_loop() -> dict[str, Any]:
    """Test run_in_executor in SelectorEventLoop (uvicorn default)."""
    print("\n--- Testing run_in_executor in SelectorEventLoop ---")

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(test_solution2_executor())
        return result
    finally:
        loop.close()


# =============================================================================
# Comparison and evaluation
# =============================================================================


def evaluate_solutions() -> None:
    """Run comprehensive evaluation of both solutions."""
    print_section("Windows asyncio Subprocess Solution Evaluation")
    print(f"Python: {sys.version}")
    print(f"Platform: {sys.platform}")

    results: dict[str, Any] = {}

    # Test 1: uvicorn default (should fail)
    print_section("Test 1: uvicorn Default Loop (SelectorEventLoop)")
    results["uvicorn_default"] = simulate_uvicorn_default_loop()
    print(f"Result: {results['uvicorn_default']}")

    # Test 2: Solution 1 - Proactor loop
    print_section("Test 2: Solution 1 - ProactorEventLoop")
    results["solution1_proactor"] = simulate_uvicorn_proactor_loop()
    print(f"Result: {results['solution1_proactor']}")

    # Test 3: Solution 2 - run_in_executor in Selector loop
    print_section("Test 3: Solution 2 - run_in_executor in SelectorEventLoop")
    results["solution2_executor"] = test_executor_in_selector_loop()
    print(f"Result: {results['solution2_executor']}")

    # Summary
    print_section("EVALUATION SUMMARY")

    print("\n## Solution 1: WindowsProactorEventLoopPolicy")
    print("-" * 50)
    s1_works = results["solution1_proactor"].get("success", False)
    print(f"  Works: {'✅ Yes' if s1_works else '❌ No'}")
    print("  Pros:")
    print("    + Simple one-line fix at app startup")
    print("    + No code changes to Claude SDK adapter")
    print("    + Native asyncio subprocess support")
    print("    + No threading overhead")
    print("  Cons:")
    print("    - May affect other parts of uvicorn behavior")
    print("    - Proactor loop has different characteristics than Selector")
    print("    - Some libraries may not work well with Proactor")
    print("    - uvicorn explicitly uses Selector for compatibility")

    print("\n## Solution 2: run_in_executor")
    print("-" * 50)
    s2_works = results["solution2_executor"].get("single_call", {}).get("success", False)
    print(f"  Works: {'✅ Yes' if s2_works else '❌ No'}")
    if s2_works:
        single_time = results["solution2_executor"].get("single_call_time", "N/A")
        concurrent_time = results["solution2_executor"].get("concurrent_time", "N/A")
        print(f"  Single call time: {single_time:.2f}s")
        print(f"  Concurrent time: {concurrent_time:.2f}s")
    print("  Pros:")
    print("    + Works with any event loop policy")
    print("    + No global state changes")
    print("    + Isolated to Claude adapter code")
    print("    + ThreadPool handles concurrent calls well")
    print("  Cons:")
    print("    - Adds threading complexity")
    print("    - Requires modifying ClaudeCodeAdapter")
    print("    - Cannot use native Claude SDK (need subprocess wrapper)")
    print("    - Slightly higher memory/CPU overhead")

    print("\n## RECOMMENDATION")
    print("-" * 50)
    if s1_works and s2_works:
        print("  Both solutions work. Recommended: Solution 1 (ProactorEventLoop)")
        print("  Reason: Simpler implementation, native asyncio support,")
        print("          allows using Claude SDK directly without modifications.")
    elif s1_works:
        print("  Recommended: Solution 1 (ProactorEventLoop)")
    elif s2_works:
        print("  Recommended: Solution 2 (run_in_executor)")
    else:
        print("  ⚠️ Neither solution worked - further investigation needed")


if __name__ == "__main__":
    evaluate_solutions()
