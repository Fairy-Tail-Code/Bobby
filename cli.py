"""OpenHarness CLI — entry point for the harness command."""
from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from io import TextIOWrapper
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
    get_server_log_path,
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
@click.option("--background", "-d", is_flag=True, help="Run in background")
@click.option("--foreground", "-f", is_flag=True, hidden=True, help="Run in foreground")
def server_start(background: bool, foreground: bool) -> None:
    """Start the Feishu service."""
    if background and foreground:
        raise click.UsageError("Choose either --background or --foreground, not both.")
    if background:
        _server_start_background()
        return
    try:
        asyncio.run(_server_main())
    except Exception as exc:
        from config.config import ConfigError
        if isinstance(exc, ConfigError):
            raise click.ClickException(str(exc)) from exc
        raise


@server.command("stop")
def server_stop() -> None:
    """Stop the running Feishu service."""
    pid_path = get_server_pid_path()
    if not pid_path.exists():
        click.echo("No running service found.")
        return
    try:
        pid = int(pid_path.read_text().strip())
    except ValueError:
        pid_path.unlink(missing_ok=True)
        click.echo("Service was not running (stale PID file removed).")
        return
    try:
        _terminate_background_process(pid)
        pid_path.unlink()
        click.echo(f"Service stopped (PID {pid}).")
    except (ProcessLookupError, FileNotFoundError, OSError, subprocess.CalledProcessError) as exc:
        if _is_stale_server_pid_error(exc):
            pid_path.unlink(missing_ok=True)
            click.echo("Service was not running (stale PID file removed).")
            return
        raise click.ClickException(f"Failed to stop service PID {pid}: {_format_subprocess_error(exc)}") from exc


@server.command("restart")
@click.option("--background", "-d", is_flag=True, help="Run in background after restart")
@click.option("--foreground", "-f", is_flag=True, hidden=True, help="Run in foreground after restart")
def server_restart(background: bool, foreground: bool) -> None:
    """Restart the Feishu service."""
    if background and foreground:
        raise click.UsageError("Choose either --background or --foreground, not both.")
    ctx = click.get_current_context()
    ctx.invoke(server_stop)
    if background:
        ctx.invoke(server_start, background=True, foreground=False)
    else:
        ctx.invoke(server_start, background=False, foreground=True)


def _server_main():
    from server import main as server_main
    return server_main()


def _build_server_background_command() -> list[str]:
    exe = sys.executable
    if getattr(sys, "frozen", False):
        return [exe, "server", "start", "--foreground"]
    return [exe, str(Path(__file__).resolve()), "server", "start", "--foreground"]


def _open_background_server_log() -> TextIOWrapper:
    log_path = get_server_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return log_path.open("a", encoding="utf-8")


def _is_pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, FileNotFoundError):
        return False
    except OSError:
        if sys.platform == "win32":
            return False
        raise


def _terminate_background_process(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            check=True,
            capture_output=True,
            text=True,
        )
        return
    os.kill(pid, signal.SIGTERM)


def _is_stale_server_pid_error(exc: BaseException) -> bool:
    if isinstance(exc, (ProcessLookupError, FileNotFoundError)):
        return True
    if isinstance(exc, OSError) and sys.platform == "win32":
        return True
    if isinstance(exc, subprocess.CalledProcessError) and sys.platform == "win32":
        text = _format_subprocess_error(exc).lower()
        return "access denied" in text or "not found" in text or "no running instance" in text
    return False


def _format_subprocess_error(exc: BaseException) -> str:
    if isinstance(exc, subprocess.CalledProcessError):
        parts = []
        if exc.stdout:
            parts.append(str(exc.stdout).strip())
        if exc.stderr:
            parts.append(str(exc.stderr).strip())
        if parts:
            return " | ".join(parts)
        return f"exit status {exc.returncode}"
    return str(exc)


def _server_start_background():
    pid_path = get_server_pid_path()
    if pid_path.exists():
        try:
            pid = int(pid_path.read_text().strip())
            if _is_pid_running(pid):
                click.echo(f"Service already running (PID {pid}). Use 'harness server stop' first.")
                return
            pid_path.unlink()
        except (ValueError, FileNotFoundError):
            pid_path.unlink(missing_ok=True)

    cmd = _build_server_background_command()
    log_file = _open_background_server_log()
    kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": log_file,
        "stderr": subprocess.STDOUT,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        proc = subprocess.Popen(cmd, **kwargs)
    finally:
        if log_file is not None:
            log_file.close()

    time.sleep(1.0)
    if proc.poll() is not None:
        raise click.ClickException(
            f"Service failed to start in background (exit code {proc.returncode}). "
            f"See {get_server_log_path()} for details."
        )

    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(proc.pid))
    click.echo(f"Service started in background (PID {proc.pid}). Logs: {get_server_log_path()}")


@server.command("logs")
def server_logs() -> None:
    """Print the current server log path."""
    click.echo(get_server_log_path())


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
    for name in ["harness.yaml", "mcp.yaml", "skill.yaml"]:
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

    env_example_dst = get_home() / ".env.example"
    env_dst = get_env_path()
    env_src = defaults / ".env.example"
    if not env_example_dst.exists() and env_src.exists():
        env_example_dst.write_text(env_src.read_text(encoding="utf-8"), encoding="utf-8")
        click.echo("  Installed .env.example")
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
            "installed_at": datetime.now(tz=None).isoformat(),
            "platform": sys.platform,
            "channel": "cli-install",
        }
        marker_path.write_text(json.dumps(marker, indent=2), encoding="utf-8")
        click.echo("  Wrote install marker")

    click.echo(f"\nInstallation complete!")
    click.echo(f"  Home: {home}")
    click.echo(f"  Config: {config_dir}")
    click.echo(f"\nRun 'harness setup' to configure your API keys, or edit {get_env_path()} manually.")


# --- harness setup ---

_PROVIDERS = {
    "1": ("OpenAI", "https://api.openai.com/v1", "gpt-4o"),
    "2": ("Zhipu / GLM", "https://open.bigmodel.cn/api/paas/v4", "GLM-4-Plus"),
    "3": ("DeepSeek", "https://api.deepseek.com", "deepseek-chat"),
    "4": ("Anthropic / Claude", "https://api.anthropic.com", "claude-sonnet-4-20250514"),
}


@cli.command()
def setup() -> None:
    """Interactive configuration wizard for API keys."""
    env_path = get_env_path()

    # Check if .env already has keys
    if env_path.exists():
        content = env_path.read_text(encoding="utf-8")
        import re
        if re.search(r'_API_KEY=\S+', content):
            if not click.confirm("  .env already has API keys. Reconfigure?"):
                return

    click.echo("")
    click.echo("  ── Configuration Wizard ──")
    click.echo("")

    click.echo("  Which LLM provider do you want to use?")
    for k, (name, _, _) in _PROVIDERS.items():
        click.echo(f"    {k}) {name}")
    click.echo("    5) Other (custom base URL)")

    choice = click.prompt("  Enter choice", default="1", show_default=False)
    if choice in _PROVIDERS:
        _, default_url, default_model = _PROVIDERS[choice]
    else:
        default_url, default_model = "", ""

    base_url = click.prompt("  Base URL", default=default_url)
    model = click.prompt("  Model name", default=default_model)
    api_key = click.prompt("  API Key", hide_input=True)
    if not api_key:
        click.echo("  No API key provided. You can edit .env later.")
        return

    same_all = click.confirm("  Use same config for all 4 agents (PM, Planner, Generator, Evaluator)?", default=True)

    roles = [("PM", "0.7"), ("PLANNER", "0.7"), ("GENERATOR", "0.4"), ("EVALUATOR", "0.2")]
    lines = []

    for prefix, temp in roles:
        if same_all:
            r_model, r_url, r_key = model, base_url, api_key
        else:
            click.echo(f"\n  ── {prefix} Agent ──")
            r_model = click.prompt("  Model", default=model)
            r_url = click.prompt("  Base URL", default=base_url)
            r_key = click.prompt("  API Key", default=api_key, hide_input=True)
        lines.append(f"{prefix}_MODEL={r_model}")
        lines.append(f"{prefix}_BASE_URL={r_url}")
        lines.append(f"{prefix}_API_KEY={r_key}")
        lines.append(f"{prefix}_TEMPERATURE={temp}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    click.echo(f"\n  Configuration saved to {env_path}")


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
