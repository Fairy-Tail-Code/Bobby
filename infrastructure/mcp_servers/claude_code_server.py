"""Claude Code MCP server — wraps `claude -p` for non-interactive AI coding delegation.

Provides tools to run Claude Code in pipe mode so that orchestrator agents can
delegate coding tasks to a dedicated Claude Code subprocess instead of using
acpx (which is subject to rate limiting).

Tools:
  - claude_prompt:  one-shot `claude -p` execution with output capture
  - claude_prompt_file:  `claude -p` with prompt read from a file (for long prompts)
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from utils.paths import get_default_runtime_cwd

claude_code_server = FastMCP("openharness-claude-code", log_level="ERROR")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_OUTPUT_CHARS = 80_000
_DEFAULT_TIMEOUT_MS = 600_000  # 10 minutes


def _find_claude_binary() -> str:
    """Locate the claude CLI on PATH."""
    claude_path = shutil.which("claude")
    if claude_path is None:
        raise FileNotFoundError(
            "Could not find 'claude' on PATH. Install Claude Code CLI first."
        )
    return claude_path


def _truncate(text: str | None, limit: int = _MAX_OUTPUT_CHARS) -> str:
    """Keep head + tail of output with a truncation notice."""
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    head = int(limit * 0.7)
    tail = int(limit * 0.2)
    omitted = len(text) - head - tail
    return (
        text[:head]
        + f"\n\n... TRUNCATED {omitted:,} chars (total {len(text):,}) ...\n\n"
        + text[-tail:]
    )


def _resolve_cwd(cwd: str | None) -> str:
    """Resolve the effective working directory."""
    if cwd is None:
        return str(get_default_runtime_cwd())
    return str(Path(cwd).expanduser().resolve(strict=False))


def build_claude_code_server() -> FastMCP:
    """Return the configured claude_code MCP server instance."""
    return claude_code_server


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@claude_code_server.tool(
    description=(
        "Run a one-shot Claude Code prompt via `claude -p`. "
        "Use this to delegate coding tasks (write code, fix bugs, refactor, etc.) "
        "to a Claude Code subprocess. Returns the full text output. "
        "For very long prompts, prefer `claude_prompt_file` to avoid shell escaping issues."
    ),
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        openWorldHint=True,
    ),
)
async def claude_prompt(
    prompt: str,
    cwd: str | None = None,
    model: str | None = None,
    timeout_ms: int = _DEFAULT_TIMEOUT_MS,
    allowed_tools: list[str] | None = None,
    disallowed_tools: list[str] | None = None,
    append_system_prompt: str | None = None,
) -> dict[str, Any]:
    """Execute `claude -p` with the given prompt and return structured output."""
    if not prompt.strip():
        raise ValueError("Tool 'claude_prompt' field 'prompt' must be a non-empty string.")
    if timeout_ms <= 0:
        raise ValueError("Tool 'claude_prompt' field 'timeout_ms' must be a positive integer.")

    cmd = _build_claude_command(
        cwd=cwd,
        model=model,
        allowed_tools=allowed_tools,
        disallowed_tools=disallowed_tools,
        append_system_prompt=append_system_prompt,
    )
    cmd.append(prompt)

    return await _run_claude(cmd, cwd=cwd, timeout_ms=timeout_ms)


@claude_code_server.tool(
    description=(
        "Run a one-shot Claude Code prompt read from a file via `claude -p`. "
        "Use this when the prompt is too long for a direct argument (avoids shell "
        "escaping and command-line length limits). The file is piped to claude via stdin."
    ),
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        openWorldHint=True,
    ),
)
async def claude_prompt_file(
    file_path: str,
    cwd: str | None = None,
    model: str | None = None,
    timeout_ms: int = _DEFAULT_TIMEOUT_MS,
    allowed_tools: list[str] | None = None,
    disallowed_tools: list[str] | None = None,
    append_system_prompt: str | None = None,
) -> dict[str, Any]:
    """Execute `claude -p` with prompt read from a file (piped via stdin)."""
    resolved = Path(file_path).expanduser().resolve(strict=False)
    if not resolved.is_file():
        raise ValueError(f"File '{resolved}' does not exist.")

    prompt_text = resolved.read_text(encoding="utf-8")
    if not prompt_text.strip():
        raise ValueError(f"File '{resolved}' is empty.")

    cmd = _build_claude_command(
        cwd=cwd,
        model=model,
        allowed_tools=allowed_tools,
        disallowed_tools=disallowed_tools,
        append_system_prompt=append_system_prompt,
    )

    return await _run_claude(cmd, cwd=cwd, timeout_ms=timeout_ms, stdin_text=prompt_text)


# ---------------------------------------------------------------------------
# Command builder
# ---------------------------------------------------------------------------

def _build_claude_command(
    *,
    cwd: str | None = None,
    model: str | None = None,
    allowed_tools: list[str] | None = None,
    disallowed_tools: list[str] | None = None,
    append_system_prompt: str | None = None,
) -> list[str]:
    """Build the base `claude -p` command with common flags."""
    claude_bin = _find_claude_binary()
    cmd: list[str] = [claude_bin, "-p", "--output-format", "text"]

    if model:
        cmd.extend(["--model", model])

    if allowed_tools:
        cmd.extend(["--allowedTools", ",".join(allowed_tools)])

    if disallowed_tools:
        cmd.extend(["--disallowedTools", ",".join(disallowed_tools)])

    if append_system_prompt:
        cmd.extend(["--append-system-prompt", append_system_prompt])

    # Skip permission prompts in delegated mode
    cmd.append("--dangerously-skip-permissions")

    return cmd


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

async def _run_claude(
    cmd: list[str],
    *,
    cwd: str | None = None,
    timeout_ms: int = _DEFAULT_TIMEOUT_MS,
    stdin_text: str | None = None,
) -> dict[str, Any]:
    """Run the claude CLI and capture output."""
    effective_cwd = _resolve_cwd(cwd)

    try:
        completed = await asyncio.to_thread(
            subprocess.run,
            cmd,
            cwd=effective_cwd,
            env=_build_env(),
            shell=False,
            text=True,
            capture_output=True,
            input=stdin_text,
            timeout=timeout_ms / 1000.0,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "cmd": " ".join(cmd),
            "cwd": effective_cwd,
            "stdout": "",
            "stderr": f"Timed out after {timeout_ms / 1000:.0f}s. Consider increasing timeout_ms.",
            "exit_code": -1,
        }
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "cmd": " ".join(cmd),
            "cwd": effective_cwd,
            "stdout": "",
            "stderr": str(exc),
            "exit_code": -1,
        }
    except Exception as exc:
        return {
            "ok": False,
            "cmd": " ".join(cmd),
            "cwd": effective_cwd,
            "stdout": "",
            "stderr": f"Execution failed: {exc}",
            "exit_code": -1,
        }

    return {
        "ok": completed.returncode == 0,
        "cmd": " ".join(cmd),
        "cwd": effective_cwd,
        "stdout": _truncate(completed.stdout),
        "stderr": _truncate(completed.stderr),
        "exit_code": completed.returncode,
    }


def _build_env() -> dict[str, str]:
    """Build the subprocess environment, ensuring no interactive terminal issues."""
    env = dict(os.environ)
    env.setdefault("CLAUDE_CODE_NON_INTERACTIVE", "1")
    return env


def main() -> None:
    """Run the claude_code MCP server over stdio."""
    build_claude_code_server().run(transport="stdio")


if __name__ == "__main__":
    main()
