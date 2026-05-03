"""CLI channel adapter — terminal-based HITL for AG2 OpenHarness.

Reads user input from stdin when the agent needs human feedback.
Uses asyncio.Future so the async event loop can block on stdin
without stalling.
"""
from __future__ import annotations

import asyncio
import sys

from infrastructure.channel.channel import ChannelAdapter
from infrastructure.frontend_cli import print_prompt


class CLIChannel(ChannelAdapter):
    """Channel adapter that reads replies from terminal stdin.

    Uses a single pending Future.  ``send()`` prints the agent question
    and registers the future; ``wait_reply()`` awaits it; external code
    (the REPL loop) calls ``inject_reply()`` to feed the response.
    """

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[str]] = {}

    async def send(self, recipient: str, subject: str, body: str, request_id: str) -> None:
        print_prompt(agent_name=recipient or None)
        if subject:
            print(f"  {subject}")
        if body:
            for line in body.splitlines():
                print(f"  {line}")
        loop = asyncio.get_running_loop()
        self._pending[request_id] = loop.create_future()

    async def poll_reply(self, request_id: str) -> str | None:
        future = self._pending.get(request_id)
        if future is None:
            return None
        if future.done():
            return future.result()
        return None

    async def wait_reply(self, request_id: str, timeout: float = 300) -> str:
        future = self._pending.get(request_id)
        if future is None:
            return "[ERROR] No pending request"
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return "[TIMEOUT] No response received, agent will continue."
        finally:
            self._pending.pop(request_id, None)

    def inject_reply(self, request_id: str, text: str) -> bool:
        future = self._pending.get(request_id)
        if future is None or future.done():
            return False
        future.set_result(text)
        return True

    def get_any_pending_request_id(self) -> str | None:
        for rid, future in self._pending.items():
            if not future.done():
                return rid
        return None

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()
