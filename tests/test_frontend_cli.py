from __future__ import annotations

import asyncio
import io
import sys

from fronted.frontend_cli import CLIFrontend


def test_cli_frontend_deduplicates_streamed_final_message(monkeypatch) -> None:
    frontend = CLIFrontend()
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)

    asyncio.run(frontend.stream_token("chat-1", "PM", "你"))
    asyncio.run(frontend.stream_token("chat-1", "PM", "好"))
    asyncio.run(frontend.send_text("chat-1", "【PM】\n你好"))

    output = stdout.getvalue()
    assert "【PM】" not in output
    assert output.endswith("\n")
