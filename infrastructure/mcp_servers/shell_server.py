"""Shell MCP server with safety guardrails inspired by Claude Code / Codex sandboxes.

Safety layers:
1. Block dangerous command patterns (recursive ops, system destruction, etc.)
2. Block interactive commands that hang the stdio channel
3. Truncate output to prevent context explosion
4. Timeout enforcement (already existed, kept)
"""
from __future__ import annotations

import asyncio
import re
import subprocess
import os
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock, Thread
from typing import Any
from uuid import uuid4

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

shell_server = FastMCP("openharness-shell", log_level="ERROR")

# ---------------------------------------------------------------------------
# Safety: command validation
# ---------------------------------------------------------------------------

_BLOCKED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # --- recursive directory traversal (context explosion) ---
    (
        re.compile(r"\bdir\s+/s\b", re.IGNORECASE),
        "Recursive `dir /s` can produce massive output. Use workspace `list_files` instead.",
    ),
    (
        re.compile(r"\btree\s+/f\b", re.IGNORECASE),
        "Recursive `tree /f` can produce massive output. Use workspace `list_files` instead.",
    ),
    (
        re.compile(r"\bGet-ChildItem\s+-Recurse\b", re.IGNORECASE),
        "Recursive listing can produce massive output. Use workspace `list_files` instead.",
    ),
    (
        re.compile(r"\bfind\s+\.\s+-type\b"),
        "Recursive `find` can produce massive output. Use workspace `list_files` instead.",
    ),
    (
        re.compile(r"\bfind\s+/[sr]\b", re.IGNORECASE),
        "Recursive `find` can produce massive output. Use workspace `list_files` instead.",
    ),
    # --- destructive file / directory operations ---
    (
        re.compile(r"\brm\s+-rf\s+/"),
        "Recursive force-delete from root is not allowed.",
    ),
    (
        re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*\s+/"),
        "Recursive delete from root is not allowed.",
    ),
    (
        re.compile(r"\brmdir\s+/s\b", re.IGNORECASE),
        "Recursive `rmdir /s` is not allowed. Delete directories explicitly.",
    ),
    (
        re.compile(r"\bdel\s+/[sf]\b", re.IGNORECASE),
        "Recursive/force delete is not allowed. Delete files explicitly.",
    ),
    (
        re.compile(r"\brd\s+/[sf]\b", re.IGNORECASE),
        "Recursive/force delete is not allowed. Delete directories explicitly.",
    ),
    # --- system-level operations ---
    (
        re.compile(r"\b(format\s+[a-zA-Z]:)\b", re.IGNORECASE),
        "Disk format is not allowed.",
    ),
    (
        re.compile(r"\bdd\s+if="),
        "Raw disk operations are not allowed.",
    ),
    (
        re.compile(r"\b(shutdown|reboot|halt|poweroff)\b", re.IGNORECASE),
        "System power commands are not allowed.",
    ),
    (
        re.compile(r"\breg\s+(add|delete|import)\b", re.IGNORECASE),
        "Registry modification is not allowed.",
    ),
    (
        re.compile(r"\bbcdedit\b", re.IGNORECASE),
        "Boot configuration modification is not allowed.",
    ),
    (
        re.compile(r"\bdiskpart\b", re.IGNORECASE),
        "Disk partition management is not allowed.",
    ),
    # --- network exfiltration ---
    (
        re.compile(r"\bcurl\b.*\|\s*(bash|sh|pwsh|python)"),
        "Piping remote content to a shell is not allowed.",
    ),
    (
        re.compile(r"\bwget\b.*\|\s*(bash|sh|pwsh|python)"),
        "Piping remote content to a shell is not allowed.",
    ),
    (
        re.compile(r"\biex\b.*\b(irm|Invoke-WebRequest)\b"),
        "PowerShell remote script execution is not allowed.",
    ),
    # --- interactive commands (hang stdio MCP channel) ---
    (
        re.compile(r"\b(python|node|ipython|php|irb|lua|sqlite3|mysql|psql)\s*$"),
        "Interactive REPLs are not allowed. Run non-interactive commands only.",
    ),
    (
        re.compile(r"\b(vim|vi|nano|emacs|less|more|code)\b"),
        "Interactive editors/pagers are not allowed.",
    ),
    (
        re.compile(r"\b(cmd|powershell|bash|sh|zsh)\s*$"),
        "Interactive subshells are not allowed. Run specific commands instead.",
    ),
    (
        re.compile(r"\bssh\s+"),
        "Interactive SSH sessions are not allowed.",
    ),
    (
        re.compile(r"\btelnet\b"),
        "Interactive telnet sessions are not allowed.",
    ),
]

# Write-like command patterns that modify filesystem
_WRITE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(git\s+push|git\s+reset\s+--hard|git\s+clean)\b", re.IGNORECASE),
]


def _validate_command(cmd: str) -> str | None:
    """Return a human-readable rejection reason, or None if the command is safe."""
    for pattern, reason in _BLOCKED_PATTERNS:
        if pattern.search(cmd):
            return reason
    return None


# ---------------------------------------------------------------------------
# Safety: output truncation
# ---------------------------------------------------------------------------

_MAX_OUTPUT_CHARS = 50_000


def _truncate(text: str, limit: int = _MAX_OUTPUT_CHARS) -> str:
    """Keep head + tail of output, inject a truncation notice in the middle."""
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


# ---------------------------------------------------------------------------
# Background command sessions
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class CommandSession:
    """Track one background shell command and its accumulated output."""

    process: subprocess.Popen[str]
    stdout_chunks: list[str] = field(default_factory=list)
    stderr_chunks: list[str] = field(default_factory=list)
    lock: Lock = field(default_factory=Lock)


_SESSIONS: dict[str, CommandSession] = {}
_SESSIONS_LOCK = Lock()


def build_shell_server() -> FastMCP:
    """Return the configured shell MCP server instance."""
    return shell_server


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@shell_server.tool(
    description="Run one shell command and wait for completion.",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        openWorldHint=True,
    ),
)
async def run_command(
    cmd: str,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    timeout_ms: int = 120_000,
) -> dict[str, Any]:
    """Run one shell command to completion and capture its output."""
    if not cmd.strip():
        raise ValueError("Tool 'run_command' field 'cmd' must be a non-empty string.")
    if timeout_ms <= 0:
        raise ValueError("Tool 'run_command' field 'timeout_ms' must be a positive integer.")

    rejection = _validate_command(cmd)
    if rejection:
        return {
            "ok": False,
            "cmd": cmd,
            "cwd": str(_resolve_cwd(cwd)),
            "stdout": "",
            "stderr": f"Command blocked: {rejection}",
            "exit_code": -1,
        }

    try:
        completed_process = await asyncio.to_thread(
            subprocess.run,
            cmd,
            cwd=_resolve_cwd(cwd),
            env=_build_command_env(env),
            shell=True,
            text=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,  # 防止子进程继承 MCP stdin 管道导致死锁
            timeout=timeout_ms / 1000.0,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "cmd": cmd,
            "cwd": str(_resolve_cwd(cwd)),
            "stdout": "",
            "stderr": f"Command timed out after {timeout_ms / 1000:.0f}s. Use start_command for long-running processes.",
            "exit_code": -1,
        }
    except Exception as exc:
        return {
            "ok": False,
            "cmd": cmd,
            "cwd": str(_resolve_cwd(cwd)),
            "stdout": "",
            "stderr": f"Command failed to execute: {exc}",
            "exit_code": -1,
        }
    return {
        "ok": completed_process.returncode == 0,
        "cmd": cmd,
        "cwd": str(_resolve_cwd(cwd)),
        "stdout": _truncate(completed_process.stdout),
        "stderr": _truncate(completed_process.stderr),
        "exit_code": completed_process.returncode,
    }


@shell_server.tool(
    description="Start one background shell command and return a session id.",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        openWorldHint=True,
    ),
)
async def start_command(
    cmd: str,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Start one shell command without waiting for completion."""
    if not cmd.strip():
        raise ValueError("Tool 'start_command' field 'cmd' must be a non-empty string.")

    rejection = _validate_command(cmd)
    if rejection:
        return {
            "ok": False,
            "session_id": "",
            "cmd": cmd,
            "cwd": str(_resolve_cwd(cwd)),
            "error": f"Command blocked: {rejection}",
        }

    process = await asyncio.to_thread(
        subprocess.Popen,
        cmd,
        cwd=_resolve_cwd(cwd),
        env=_build_command_env(env),
        shell=True,
        text=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
    )
    session_id = str(uuid4())
    session = CommandSession(process=process)
    with _SESSIONS_LOCK:
        _SESSIONS[session_id] = session
    _start_stream_reader(session=session, stream_name="stdout")
    _start_stream_reader(session=session, stream_name="stderr")
    return {
        "ok": True,
        "session_id": session_id,
        "cmd": cmd,
        "cwd": str(_resolve_cwd(cwd)),
    }


@shell_server.tool(
    description="Read command output from one background session.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def read_command_output(
    session_id: str,
    stdout_cursor: int = 0,
    stderr_cursor: int = 0,
) -> dict[str, Any]:
    """Read accumulated stdout and stderr for one background command."""
    session = _get_required_session(session_id)
    with session.lock:
        stdout_value = "".join(session.stdout_chunks)
        stderr_value = "".join(session.stderr_chunks)
    exit_code = session.process.poll()
    return {
        "ok": True,
        "session_id": session_id,
        "stdout": _truncate(stdout_value[stdout_cursor:]),
        "stderr": _truncate(stderr_value[stderr_cursor:]),
        "stdout_cursor": len(stdout_value),
        "stderr_cursor": len(stderr_value),
        "running": exit_code is None,
        "exit_code": exit_code,
    }


@shell_server.tool(
    description="Write stdin to one background command session.",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        openWorldHint=True,
    ),
)
async def write_stdin(session_id: str, chars: str) -> dict[str, Any]:
    """Write characters to one running command session stdin."""
    session = _get_required_session(session_id)
    if session.process.stdin is None:
        raise ValueError(f"Session '{session_id}' does not accept stdin.")
    await asyncio.to_thread(session.process.stdin.write, chars)
    await asyncio.to_thread(session.process.stdin.flush)
    return {
        "ok": True,
        "session_id": session_id,
        "chars_written": len(chars),
    }


@shell_server.tool(
    description="Terminate one background command session.",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        openWorldHint=True,
    ),
)
async def terminate_command(session_id: str) -> dict[str, Any]:
    """Terminate one background command and return its last known state."""
    session = _get_required_session(session_id)
    if session.process.poll() is None:
        session.process.terminate()
        try:
            await asyncio.to_thread(session.process.wait, timeout=5.0)
        except subprocess.TimeoutExpired:
            session.process.kill()
            await asyncio.to_thread(session.process.wait, timeout=5.0)
    return {
        "ok": True,
        "session_id": session_id,
        "exit_code": session.process.poll(),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _start_stream_reader(*, session: CommandSession, stream_name: str) -> None:
    """Start one daemon thread that drains a subprocess stream into memory."""
    stream = getattr(session.process, stream_name)
    if stream is None:
        return

    def _reader() -> None:
        for chunk in iter(stream.readline, ""):
            if not chunk:
                break
            with session.lock:
                if stream_name == "stdout":
                    session.stdout_chunks.append(chunk)
                else:
                    session.stderr_chunks.append(chunk)
        stream.close()

    Thread(target=_reader, daemon=True, name=f"openharness-{stream_name}-reader").start()


def _get_required_session(session_id: str) -> CommandSession:
    """Return one active session or raise a validation error."""
    with _SESSIONS_LOCK:
        session = _SESSIONS.get(session_id)
    if session is None:
        raise ValueError(f"No shell session '{session_id}' is active.")
    return session


def _build_command_env(extra_env: dict[str, str] | None) -> dict[str, str]:
    """Merge the current environment with one command-local override map."""
    merged_env = dict(os.environ)
    if extra_env is not None:
        merged_env.update(extra_env)
    return merged_env


def _resolve_cwd(cwd: str | None) -> str:
    """Return the effective working directory for one command invocation."""
    if cwd is None:
        return str(Path.cwd().resolve())
    return str(Path(cwd).expanduser().resolve(strict=False))


def main() -> None:
    """Run the shell MCP server over stdio."""
    build_shell_server().run(transport="stdio")


if __name__ == "__main__":
    main()
