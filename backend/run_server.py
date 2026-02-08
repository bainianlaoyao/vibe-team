"""
Custom uvicorn runner with ProactorEventLoop for Windows.

This script ensures that asyncio.create_subprocess_exec works correctly
on Windows by using ProactorEventLoop instead of SelectorEventLoop.

Usage: uv run python run_server.py
"""

from __future__ import annotations

import asyncio
import sys

# Windows: Must set ProactorEventLoop BEFORE importing uvicorn
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from uvicorn import Config, Server


class ProactorServer(Server):
    """Custom uvicorn server that uses ProactorEventLoop on Windows."""

    def run(self, sockets=None):
        if sys.platform == "win32":
            # Create a new ProactorEventLoop for this server
            loop = asyncio.ProactorEventLoop()
            asyncio.set_event_loop(loop)
        return asyncio.run(self.serve(sockets=sockets))


def main():
    config = Config(
        app="app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=["app"],
    )

    server = ProactorServer(config=config)
    server.run()


if __name__ == "__main__":
    main()
