from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
import subprocess
from threading import Lock, Thread
from uuid import uuid4
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations


shell_server = FastMCP("openharness-shell", log_level="ERROR")


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


@shell_server.tool(
    description="Run one shell command and wait for completion.",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        openWorldHint=True,
    ),
)
def run_command(
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
    completed_process = subprocess.run(
        cmd,
        cwd=_resolve_cwd(cwd),
        env=_build_command_env(env),
        shell=True,
        text=True,
        capture_output=True,
        timeout=timeout_ms / 1000.0,
    )
    return {
        "ok": completed_process.returncode == 0,
        "cmd": cmd,
        "cwd": str(_resolve_cwd(cwd)),
        "stdout": completed_process.stdout,
        "stderr": completed_process.stderr,
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
def start_command(
    cmd: str,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Start one shell command without waiting for completion."""
    if not cmd.strip():
        raise ValueError("Tool 'start_command' field 'cmd' must be a non-empty string.")
    process = subprocess.Popen(
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
        "stdout": stdout_value[stdout_cursor:],
        "stderr": stderr_value[stderr_cursor:],
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
def write_stdin(session_id: str, chars: str) -> dict[str, Any]:
    """Write characters to one running command session stdin."""
    session = _get_required_session(session_id)
    if session.process.stdin is None:
        raise ValueError(f"Session '{session_id}' does not accept stdin.")
    session.process.stdin.write(chars)
    session.process.stdin.flush()
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
def terminate_command(session_id: str) -> dict[str, Any]:
    """Terminate one background command and return its last known state."""
    session = _get_required_session(session_id)
    if session.process.poll() is None:
        session.process.terminate()
        try:
            session.process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            session.process.kill()
            session.process.wait(timeout=5.0)
    return {
        "ok": True,
        "session_id": session_id,
        "exit_code": session.process.poll(),
    }


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
