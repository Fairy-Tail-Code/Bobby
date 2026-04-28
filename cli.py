"""OpenHarness CLI — entry point for the harness command."""
from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import click

from infrastructure.paths import (
    VERSION,
    ensure_dirs,
    get_config_dir,
    get_defaults_dir,
    get_env_path,
    get_home,
    get_install_marker_path,
    get_memory_dir,
    get_server_pid_path,
    get_session_dir,
    get_system_skills_dir,
    get_user_skills_dir,
    get_workspace_dir,
)


@click.group()
@click.version_option(VERSION, prog_name="harness")
def cli():
    """OpenHarness — Multi-agent full-stack application generation harness."""


# --- harness run <prompt> ---

@cli.command()
@click.argument("prompt", nargs=-1, required=True)
def run(prompt: tuple[str, ...]) -> None:
    """Run a task with the given prompt (CLI mode)."""
    from main import run as _run
    asyncio.run(_run(" ".join(prompt)))


# --- harness server start/stop/restart ---

@cli.group()
def server():
    """Manage the Feishu service."""


@server.command("start")
@click.option("--foreground", "-f", is_flag=True, help="Run in foreground")
def server_start(foreground: bool) -> None:
    """Start the Feishu service."""
    if foreground:
        asyncio.run(_server_main())
    else:
        _server_start_background()


@server.command("stop")
def server_stop() -> None:
    """Stop the running Feishu service."""
    pid_path = get_server_pid_path()
    if not pid_path.exists():
        click.echo("No running service found.")
        return
    pid = int(pid_path.read_text().strip())
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=True, capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
        pid_path.unlink()
        click.echo(f"Service stopped (PID {pid}).")
    except (ProcessLookupError, FileNotFoundError):
        pid_path.unlink()
        click.echo("Service was not running (stale PID file removed).")


@server.command("restart")
def server_restart() -> None:
    """Restart the Feishu service."""
    ctx = click.get_current_context()
    ctx.invoke(server_stop)
    ctx.invoke(server_start)


def _server_main():
    from server import main as server_main
    return server_main()


def _server_start_background():
    pid_path = get_server_pid_path()
    if pid_path.exists():
        try:
            pid = int(pid_path.read_text().strip())
            os.kill(pid, 0)
            click.echo(f"Service already running (PID {pid}). Use 'harness server stop' first.")
            return
        except (ProcessLookupError, FileNotFoundError):
            pid_path.unlink()

    exe = sys.executable
    if getattr(sys, "frozen", False):
        cmd = [exe, "server", "start", "--foreground"]
    else:
        cmd = [exe, str(Path(__file__).resolve()), "server", "start", "--foreground"]

    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    proc = subprocess.Popen(cmd, **kwargs)
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(proc.pid))
    click.echo(f"Service started in background (PID {proc.pid}).")


# --- harness knowledge sync/search/status ---

@cli.group()
def knowledge():
    """Manage the knowledge base."""


@knowledge.command("sync")
def knowledge_sync() -> None:
    """Sync knowledge with the server."""
    from config.config import load_knowledge_config
    from main import _knowledge_sync
    config = load_knowledge_config()
    asyncio.run(_knowledge_sync(config))


@knowledge.command("search")
@click.argument("query", nargs=-1, required=True)
def knowledge_search(query: tuple[str, ...]) -> None:
    """Search the knowledge base."""
    from config.config import load_knowledge_config
    from main import _knowledge_search
    config = load_knowledge_config()
    asyncio.run(_knowledge_search(config, " ".join(query)))


@knowledge.command("status")
def knowledge_status() -> None:
    """Show knowledge base status."""
    from config.config import load_knowledge_config
    from main import _knowledge_status
    config = load_knowledge_config()
    asyncio.run(_knowledge_status(config))


# --- harness _mcp <name> (hidden) ---

_MCP_SERVERS = {
    "shell": "infrastructure.mcp_servers.shell_server",
    "git": "infrastructure.mcp_servers.git_server",
    "browser": "infrastructure.mcp_servers.browser_server",
    "workspace": "infrastructure.mcp_servers.workspace_server",
    "docker": "infrastructure.mcp_servers.docker_server",
    "database": "infrastructure.mcp_servers.database_server",
    "http_api": "infrastructure.mcp_servers.http_api_server",
    "docs_web": "infrastructure.mcp_servers.docs_web_server",
    "gitee": "infrastructure.mcp_servers.gitee_server",
    "claude_code": "infrastructure.mcp_servers.claude_code_server",
}


@cli.group(hidden=True)
def _mcp():
    """Internal: run MCP servers."""


for _name, _module in _MCP_SERVERS.items():
    def _make_mcp_command(mod):
        @click.command(name=mod.split(".")[-1].replace("_server", ""))
        def _mcp_cmd():
            import importlib
            m = importlib.import_module(mod)
            m.main()
        return _mcp_cmd
    _mcp.add_command(_make_mcp_command(_module))


# --- harness install ---

@cli.command()
def install() -> None:
    """Initialize or repair ~/.openharness/ configuration."""
    home = get_home()
    defaults = get_defaults_dir()

    ensure_dirs()
    click.echo(f"Created directory structure at {home}")

    config_dir = get_config_dir()
    for name in ["harness.yaml", "mcp.yaml", "skill.yaml", ".env.example"]:
        src = defaults / name
        dst = config_dir / name
        if dst.exists():
            click.echo(f"  Skipped {name} (already exists)")
        elif src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            click.echo(f"  Installed {name}")
        else:
            click.echo(f"  Warning: template {name} not found at {src}")

    env_dst = get_env_path()
    env_src = defaults / ".env.example"
    if not env_dst.exists() and env_src.exists():
        env_dst.write_text(env_src.read_text(encoding="utf-8"), encoding="utf-8")
        click.echo("  Installed .env (from .env.example)")

    profile_dst = get_memory_dir() / "user_profile.md"
    profile_src = defaults / "user_profile.md"
    if not profile_dst.exists() and profile_src.exists():
        profile_dst.write_text(profile_src.read_text(encoding="utf-8"), encoding="utf-8")
        click.echo("  Installed user_profile.md")

    marker_path = get_install_marker_path()
    if not marker_path.exists():
        marker = {
            "version": VERSION,
            "installed_at": datetime.utcnow().isoformat() + "Z",
            "platform": sys.platform,
            "channel": "cli-install",
        }
        marker_path.write_text(json.dumps(marker, indent=2), encoding="utf-8")
        click.echo("  Wrote install marker")

    click.echo(f"\nInstallation complete!")
    click.echo(f"  Home: {home}")
    click.echo(f"  Config: {config_dir}")
    click.echo(f"\nEdit {get_env_path()} with your API keys before running.")


# --- harness info ---

@cli.command()
def info() -> None:
    """Show installation information."""
    click.echo(f"OpenHarness v{VERSION}")
    click.echo(f"  Home:          {get_home()}")
    click.echo(f"  Config:        {get_config_dir()}")
    click.echo(f"  Session:       {get_session_dir()}")
    click.echo(f"  Memory:        {get_memory_dir()}")
    click.echo(f"  System Skills: {get_system_skills_dir()}")
    click.echo(f"  User Skills:   {get_user_skills_dir()}")
    click.echo(f"  Workspace:     {get_workspace_dir()}")
    click.echo(f"  .env:          {get_env_path()}")

    marker_path = get_install_marker_path()
    if marker_path.exists():
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        click.echo(f"\n  Installed: {marker.get('installed_at', 'unknown')}")
        click.echo(f"  Platform:  {marker.get('platform', 'unknown')}")
        click.echo(f"  Channel:   {marker.get('channel', 'unknown')}")
    else:
        click.echo("\n  Not installed. Run 'harness install' first.")

    pid_path = get_server_pid_path()
    if pid_path.exists():
        try:
            pid = int(pid_path.read_text().strip())
            os.kill(pid, 0)
            click.echo(f"\n  Server: running (PID {pid})")
        except (ProcessLookupError, FileNotFoundError):
            pid_path.unlink()
            click.echo(f"\n  Server: stopped (stale PID removed)")
    else:
        click.echo(f"\n  Server: stopped")


if __name__ == "__main__":
    cli()
