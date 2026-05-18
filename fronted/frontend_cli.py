"""CLI frontend — terminal-based output for AG2 OpenHarness.

Implements the Frontend Protocol with colored, streaming terminal output
in the style of OpenAI Codex CLI.
"""
from __future__ import annotations

import sys

# ANSI color codes
_COLORS = {
    "blue": "\033[94m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "magenta": "\033[95m",
    "cyan": "\033[96m",
    "red": "\033[91m",
    "white": "\033[97m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}

# Agent name -> color mapping
_AGENT_COLORS: dict[str, str] = {
    "PM": "blue",
    "Planner": "green",
    "Generator": "yellow",
    "Evaluator": "magenta",
}

# Cache for per-agent color assignment (agents not in the preset)
_AGENT_COLOR_INDEX = len(_AGENT_COLORS)
_AGENT_COLOR_ORDER = ["blue", "green", "yellow", "magenta", "cyan"]


def _agent_color(name: str) -> str:
    if name in _AGENT_COLORS:
        return _AGENT_COLORS[name]
    global _AGENT_COLOR_INDEX
    _AGENT_COLORS[name] = _AGENT_COLOR_ORDER[_AGENT_COLOR_INDEX % len(_AGENT_COLOR_ORDER)]
    _AGENT_COLOR_INDEX += 1
    return _AGENT_COLORS[name]


class CLIFrontend:
    """Terminal frontend that prints agent output with colored formatting."""

    def __init__(self) -> None:
        self._stream_buffers: dict[tuple[str, str], str] = {}

    async def send_text(self, chat_id: str, text: str) -> None:
        if self._consume_streamed_message(chat_id, text):
            sys.stdout.write("\n")
            sys.stdout.flush()
            return
        color = _COLORS["white"]
        reset = _COLORS["reset"]
        sys.stdout.write(f"\r{color}{text}{reset}\n")
        sys.stdout.flush()

    async def stream_token(self, chat_id: str, agent_name: str, token: str) -> None:
        key = (chat_id, agent_name)
        self._stream_buffers[key] = self._stream_buffers.get(key, "") + token
        color = _COLORS[_agent_color(agent_name)]
        reset = _COLORS["reset"]
        sys.stdout.write(f"{color}{token}{reset}")
        sys.stdout.flush()

    async def on_tool_call(self, chat_id: str, agent_name: str, tool_name: str) -> None:
        color = _COLORS["cyan"]
        reset = _COLORS["reset"]
        sys.stdout.write(f"\r{color}\U0001f527 {agent_name} -> {tool_name}{reset}\n")
        sys.stdout.flush()

    def _consume_streamed_message(self, chat_id: str, text: str) -> bool:
        if not text.startswith("【") or "】\n" not in text:
            self._clear_stream_state(chat_id)
            return False

        agent_name, body = text[1:].split("】\n", 1)
        key = (chat_id, agent_name)
        streamed = self._stream_buffers.get(key)
        self._clear_stream_state(chat_id)
        return streamed is not None and body == streamed

    def _clear_stream_state(self, chat_id: str) -> None:
        stale_keys = [key for key in self._stream_buffers if key[0] == chat_id]
        for key in stale_keys:
            self._stream_buffers.pop(key, None)


def print_agent_header(agent_name: str) -> None:
    color = _COLORS[_agent_color(agent_name)]
    bold = _COLORS["bold"]
    reset = _COLORS["reset"]
    sys.stdout.write(f"\n{color}{bold}[{agent_name}]{reset} ")
    sys.stdout.flush()


def print_error(text: str) -> None:
    color = _COLORS["red"]
    reset = _COLORS["reset"]
    sys.stdout.write(f"\r{color}Error: {text}{reset}\n")
    sys.stdout.flush()


def print_info(text: str) -> None:
    dim = _COLORS["dim"]
    reset = _COLORS["reset"]
    sys.stdout.write(f"{dim}{text}{reset}\n")
    sys.stdout.flush()


def print_prompt(agent_name: str | None = None) -> None:
    bold = _COLORS["bold"]
    reset = _COLORS["reset"]
    if agent_name:
        color = _COLORS[_agent_color(agent_name)]
        sys.stdout.write(f"\n{color}{bold}[{agent_name} is asking]:{reset} ")
    else:
        sys.stdout.write(f"\n{bold}You:{reset} ")
    sys.stdout.flush()
