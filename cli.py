"""OpenHarness CLI — entry point for the harness command."""
from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from io import TextIOWrapper
from pathlib import Path
from typing import Sequence

import click
import yaml

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

_LLM_ROLE_TEMPERATURES = [
    ("PM", "0.7"),
    ("PLANNER", "0.7"),
    ("GENERATOR", "0.4"),
    ("EVALUATOR", "0.2"),
]

_ROLE_LABELS = {
    "PM": "PM",
    "PLANNER": "Planner",
    "GENERATOR": "Generator",
    "EVALUATOR": "Evaluator",
}

_PROVIDER_PRESETS = {
    "openai": ("OpenAI", "https://api.openai.com/v1", "gpt-4o"),
    "zhipu": ("Zhipu / GLM", "https://open.bigmodel.cn/api/paas/v4", "GLM-4-Plus"),
    "deepseek": ("DeepSeek", "https://api.deepseek.com", "deepseek-chat"),
    "anthropic": ("Anthropic / Claude", "https://api.anthropic.com", "claude-sonnet-4-20250514"),
    "custom": ("Other (custom base URL)", "", ""),
}

_ENV_LINE_RE = re.compile(r"^([A-Za-z0-9_]+)=(.*)$")


def _ensure_setup_files() -> None:
    ensure_dirs()
    defaults_dir = get_defaults_dir()
    config_dir = get_config_dir()

    for name in ("harness.yaml", "mcp.yaml", "skill.yaml"):
        src = defaults_dir / name
        dst = config_dir / name
        if not dst.exists() and src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    env_example_path = get_env_path().with_name(".env.example")
    env_src = defaults_dir / ".env.example"
    if not env_example_path.exists() and env_src.exists():
        env_example_path.write_text(env_src.read_text(encoding="utf-8"), encoding="utf-8")
    if not get_env_path().exists() and env_example_path.exists():
        get_env_path().write_text(env_example_path.read_text(encoding="utf-8"), encoding="utf-8")


def _load_env_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def _load_setup_defaults(env_path: Path) -> dict[str, str]:
    values = _load_env_values(env_path.with_name(".env.example"))
    values.update(_load_env_values(env_path))
    return values


def _load_env_template_text(env_path: Path) -> str:
    if env_path.exists():
        return env_path.read_text(encoding="utf-8")
    env_example_path = env_path.with_name(".env.example")
    if env_example_path.exists():
        return env_example_path.read_text(encoding="utf-8")
    return ""


def _merge_env_text(base_text: str, updates: dict[str, str]) -> str:
    lines = base_text.splitlines()
    seen: set[str] = set()
    merged: list[str] = []

    for line in lines:
        match = _ENV_LINE_RE.match(line)
        if match:
            key = match.group(1)
            if key in updates:
                merged.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        merged.append(line)

    missing_keys = [key for key in updates if key not in seen]
    if missing_keys and merged and merged[-1] != "":
        merged.append("")
    for key in missing_keys:
        merged.append(f"{key}={updates[key]}")

    return "\n".join(merged).rstrip() + "\n"


def _write_env_values(env_path: Path, updates: dict[str, str]) -> None:
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text(_merge_env_text(_load_env_template_text(env_path), updates), encoding="utf-8")


def _confirm_choice(name: str, text: str, default: bool = True) -> bool:
    del name
    return click.confirm(f"  {text}", default=default)


def _prompt_value(
    name: str,
    label: str,
    default: str = "",
    secret: bool = False,
    allow_empty: bool = False,
) -> str:
    del name
    while True:
        value = click.prompt(
            f"  {label}",
            default=default or "",
            show_default=bool(default) and not secret,
            hide_input=secret,
        )
        if value or allow_empty:
            return value
        click.echo("  This value is required.")


def _render_menu(title: str, labels: Sequence[str], selected_index: int, description: str | None) -> int:
    lines = ["", f"  {title}"]
    if description:
        lines.extend(f"  {line}" for line in description.splitlines())
    lines.append("  Use Up/Down to choose, Enter to confirm.")
    lines.append("")
    for index, label in enumerate(labels):
        marker = ">" if index == selected_index else " "
        lines.append(f"  {marker} {label}")
    sys.stdout.write("".join(f"\x1b[2K{line}\n" for line in lines))
    sys.stdout.flush()
    return len(lines)


def _read_menu_key() -> str:
    if sys.platform == "win32":
        import msvcrt

        ch = msvcrt.getwch()
        if ch == "\x03":
            raise KeyboardInterrupt
        if ch in ("\x00", "\xe0"):
            next_ch = msvcrt.getwch()
            if next_ch == "H":
                return "up"
            if next_ch == "P":
                return "down"
            return ""
        if ch == "\r":
            return "enter"
        if ch == "\x1b":
            return "escape"
        if ch.lower() == "k":
            return "up"
        if ch.lower() == "j":
            return "down"
        return ""

    import select

    ch = sys.stdin.read(1)
    if ch == "\x03":
        raise KeyboardInterrupt
    if ch in ("\r", "\n"):
        return "enter"
    if ch == "\x1b":
        if select.select([sys.stdin], [], [], 0.05)[0]:
            next_ch = sys.stdin.read(1)
            if next_ch == "[" and select.select([sys.stdin], [], [], 0.05)[0]:
                final_ch = sys.stdin.read(1)
                if final_ch == "A":
                    return "up"
                if final_ch == "B":
                    return "down"
        return "escape"
    if ch.lower() == "k":
        return "up"
    if ch.lower() == "j":
        return "down"
    return ""


def _interactive_select_index(
    title: str,
    labels: Sequence[str],
    default_index: int = 0,
    description: str | None = None,
) -> int | None:
    line_count = 0
    selected_index = max(0, min(default_index, len(labels) - 1))

    if sys.platform != "win32":
        import termios
        import tty

        stdin_fd = sys.stdin.fileno()
        original_attrs = termios.tcgetattr(stdin_fd)
        try:
            tty.setraw(stdin_fd)
            while True:
                if line_count:
                    sys.stdout.write(f"\x1b[{line_count}F")
                line_count = _render_menu(title, labels, selected_index, description)
                key = _read_menu_key()
                if key == "up":
                    selected_index = (selected_index - 1) % len(labels)
                elif key == "down":
                    selected_index = (selected_index + 1) % len(labels)
                elif key == "enter":
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    return selected_index
                elif key == "escape":
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    return None
        finally:
            termios.tcsetattr(stdin_fd, termios.TCSADRAIN, original_attrs)

    while True:
        if line_count:
            sys.stdout.write(f"\x1b[{line_count}F")
        line_count = _render_menu(title, labels, selected_index, description)
        key = _read_menu_key()
        if key == "up":
            selected_index = (selected_index - 1) % len(labels)
        elif key == "down":
            selected_index = (selected_index + 1) % len(labels)
        elif key == "enter":
            sys.stdout.write("\n")
            sys.stdout.flush()
            return selected_index
        elif key == "escape":
            sys.stdout.write("\n")
            sys.stdout.flush()
            return None


def _numeric_select_option(
    title: str,
    options: Sequence[tuple[str, str]],
    default: str | None = None,
    description: str | None = None,
) -> str:
    click.echo(f"\n  {title}")
    if description:
        for line in description.splitlines():
            click.echo(f"  {line}")
    for index, (_, label) in enumerate(options, start=1):
        click.echo(f"    {index}) {label}")

    default_index = 1
    if default is not None:
        for index, (value, _) in enumerate(options, start=1):
            if value == default:
                default_index = index
                break

    choice = click.prompt("  Enter choice", default=str(default_index), show_default=False)
    try:
        selected_index = int(choice) - 1
    except ValueError:
        selected_index = default_index - 1
    if 0 <= selected_index < len(options):
        return options[selected_index][0]
    return options[default_index - 1][0]


def _select_option(
    name: str,
    title: str,
    options: Sequence[tuple[str, str]],
    default: str | None = None,
    description: str | None = None,
) -> str:
    del name
    if not options:
        raise click.ClickException("No selectable options were provided.")

    if sys.stdin.isatty() and sys.stdout.isatty():
        default_index = 0
        if default is not None:
            for index, (value, _) in enumerate(options):
                if value == default:
                    default_index = index
                    break
        selected_index = _interactive_select_index(
            title,
            [label for _, label in options],
            default_index,
            description,
        )
        if selected_index is not None:
            return options[selected_index][0]

    return _numeric_select_option(title, options, default, description)


def _get_hitl_mode() -> str:
    harness_path = get_config_dir() / "harness.yaml"
    if not harness_path.exists():
        return "stdin"
    raw = yaml.safe_load(harness_path.read_text(encoding="utf-8")) or {}
    return raw.get("harness", {}).get("hitl", {}).get("mode", "stdin")


def _save_hitl_mode(mode: str) -> None:
    harness_path = get_config_dir() / "harness.yaml"
    if not harness_path.exists():
        return
    raw = yaml.safe_load(harness_path.read_text(encoding="utf-8")) or {}
    harness_raw = raw.setdefault("harness", {})
    hitl_raw = harness_raw.setdefault("hitl", {})
    hitl_raw["mode"] = mode
    harness_path.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _prompt_role_values(
    confirm_name: str,
    shared_prompt_name: str,
    shared_prompt_label: str,
    env_key_template: str,
    same_value_question: str,
    existing_env: dict[str, str],
) -> dict[str, str]:
    updates: dict[str, str] = {}
    if _confirm_choice(confirm_name, same_value_question, default=True):
        shared_value = _prompt_value(
            shared_prompt_name,
            shared_prompt_label,
            default=existing_env.get(env_key_template.format(prefix="PM"), ""),
        )
        for prefix, _ in _LLM_ROLE_TEMPERATURES:
            updates[env_key_template.format(prefix=prefix)] = shared_value
        return updates

    for prefix, _ in _LLM_ROLE_TEMPERATURES:
        env_key = env_key_template.format(prefix=prefix)
        updates[env_key] = _prompt_value(
            env_key,
            f"{_ROLE_LABELS[prefix]} {shared_prompt_label}",
            default=existing_env.get(env_key, ""),
        )
    return updates


def _configure_email_hitl(existing_env: dict[str, str]) -> dict[str, str]:
    updates: dict[str, str] = {}
    updates["SMTP_HOST"] = _prompt_value("SMTP_HOST", "SMTP host", existing_env.get("SMTP_HOST", "smtp.qq.com"))
    updates["SMTP_PORT"] = _prompt_value("SMTP_PORT", "SMTP port", existing_env.get("SMTP_PORT", "587"))
    updates["SMTP_USER"] = _prompt_value("SMTP_USER", "SMTP user", existing_env.get("SMTP_USER", ""))
    updates["SMTP_PASSWORD"] = _prompt_value(
        "SMTP_PASSWORD",
        "SMTP password / app password",
        existing_env.get("SMTP_PASSWORD", ""),
        secret=True,
    )
    updates["SMTP_USE_TLS"] = "true" if _confirm_choice(
        "SMTP_USE_TLS",
        "Enable SMTP TLS?",
        default=existing_env.get("SMTP_USE_TLS", "true").lower() == "true",
    ) else "false"
    updates["IMAP_HOST"] = _prompt_value("IMAP_HOST", "IMAP host", existing_env.get("IMAP_HOST", "imap.qq.com"))
    updates["IMAP_PORT"] = _prompt_value("IMAP_PORT", "IMAP port", existing_env.get("IMAP_PORT", "993"))
    updates["IMAP_USER"] = _prompt_value(
        "IMAP_USER",
        "IMAP user",
        existing_env.get("IMAP_USER", updates["SMTP_USER"]),
    )
    updates["IMAP_PASSWORD"] = _prompt_value(
        "IMAP_PASSWORD",
        "IMAP password / app password",
        existing_env.get("IMAP_PASSWORD", updates["SMTP_PASSWORD"]),
        secret=True,
    )
    updates["IMAP_USE_SSL"] = "true" if _confirm_choice(
        "IMAP_USE_SSL",
        "Enable IMAP SSL?",
        default=existing_env.get("IMAP_USE_SSL", "true").lower() == "true",
    ) else "false"
    updates.update(
        _prompt_role_values(
            "same_hitl_email",
            "shared_hitl_email",
            "human operator email",
            "HITL_{prefix}_EMAIL",
            "Use the same operator email for all roles?",
            existing_env,
        )
    )
    return updates


def _configure_dingtalk_hitl(existing_env: dict[str, str]) -> dict[str, str]:
    updates: dict[str, str] = {}
    updates["DINGTALK_CLIENT_ID"] = _prompt_value(
        "DINGTALK_CLIENT_ID",
        "DingTalk client id",
        existing_env.get("DINGTALK_CLIENT_ID", ""),
    )
    updates["DINGTALK_CLIENT_SECRET"] = _prompt_value(
        "DINGTALK_CLIENT_SECRET",
        "DingTalk client secret",
        existing_env.get("DINGTALK_CLIENT_SECRET", ""),
        secret=True,
    )
    updates["DINGTALK_ROBOT_CODE"] = _prompt_value(
        "DINGTALK_ROBOT_CODE",
        "DingTalk robot code",
        existing_env.get("DINGTALK_ROBOT_CODE", updates["DINGTALK_CLIENT_ID"]),
    )
    updates.update(
        _prompt_role_values(
            "same_hitl_dingtalk_user_id",
            "shared_hitl_dingtalk_user_id",
            "DingTalk user id",
            "HITL_{prefix}_DINGTALK_USER_ID",
            "Use the same DingTalk user id for all roles?",
            existing_env,
        )
    )
    return updates


def _configure_feishu_hitl(existing_env: dict[str, str], updates: dict[str, str]) -> dict[str, str]:
    if not updates.get("FEISHU_APP_ID"):
        updates["FEISHU_APP_ID"] = _prompt_value(
            "FEISHU_APP_ID",
            "Feishu app id",
            existing_env.get("FEISHU_APP_ID", ""),
        )
    if not updates.get("FEISHU_APP_SECRET"):
        updates["FEISHU_APP_SECRET"] = _prompt_value(
            "FEISHU_APP_SECRET",
            "Feishu app secret",
            existing_env.get("FEISHU_APP_SECRET", ""),
            secret=True,
        )
    updates.update(
        _prompt_role_values(
            "same_hitl_feishu_open_id",
            "shared_hitl_feishu_open_id",
            "Feishu open id",
            "HITL_{prefix}_FEISHU_OPEN_ID",
            "Use the same Feishu open id for all roles?",
            existing_env,
        )
    )
    return updates


@cli.command()
def setup() -> None:
    """Interactive configuration wizard for .env and HITL settings."""
    _ensure_setup_files()
    env_path = get_env_path()
    existing_env = _load_setup_defaults(env_path)

    if any(existing_env.get(f"{prefix}_API_KEY") for prefix, _ in _LLM_ROLE_TEMPERATURES):
        if not _confirm_choice("reconfigure_env", ".env already has API keys. Reconfigure?", default=False):
            return

    click.echo("")
    click.echo("  ── Configuration Wizard ──")
    click.echo("")

    provider_key = _select_option(
        "llm_provider",
        "Select the LLM provider",
        [(key, value[0]) for key, value in _PROVIDER_PRESETS.items()],
        default="openai",
        description="This fills the 4 agent model/base_url/api_key entries in ~/.openharness/.env.",
    )
    _, default_url, default_model = _PROVIDER_PRESETS[provider_key]

    base_url = _prompt_value(
        "shared_base_url",
        "Base URL",
        existing_env.get("PM_BASE_URL", default_url),
    )
    model = _prompt_value(
        "shared_model",
        "Model name",
        existing_env.get("PM_MODEL", default_model),
    )
    api_key = _prompt_value(
        "shared_api_key",
        "API key",
        existing_env.get("PM_API_KEY", ""),
        secret=True,
    )
    if not api_key:
        click.echo("  No API key provided. You can edit .env later.")
        return

    same_all = _confirm_choice(
        "same_llm_config",
        "Use the same API config for all 4 agents (PM, Planner, Generator, Evaluator)?",
        default=True,
    )

    updates: dict[str, str] = {}
    for prefix, temp in _LLM_ROLE_TEMPERATURES:
        if same_all:
            r_model, r_url, r_key = model, base_url, api_key
        else:
            click.echo(f"\n  ── {prefix} Agent ──")
            r_model = _prompt_value(f"{prefix}_MODEL", "Model", existing_env.get(f"{prefix}_MODEL", model))
            r_url = _prompt_value(f"{prefix}_BASE_URL", "Base URL", existing_env.get(f"{prefix}_BASE_URL", base_url))
            r_key = _prompt_value(
                f"{prefix}_API_KEY",
                "API key",
                existing_env.get(f"{prefix}_API_KEY", api_key),
                secret=True,
            )
        updates[f"{prefix}_MODEL"] = r_model
        updates[f"{prefix}_BASE_URL"] = r_url
        updates[f"{prefix}_API_KEY"] = r_key
        updates[f"{prefix}_TEMPERATURE"] = temp

    if _confirm_choice(
        "configure_gitee",
        "Configure optional Gitee integration now?",
        default=bool(existing_env.get("GITEE_ACCESS_TOKEN") or existing_env.get("GITEE_BASE_URL")),
    ):
        updates["GITEE_ACCESS_TOKEN"] = _prompt_value(
            "GITEE_ACCESS_TOKEN",
            "Gitee access token",
            existing_env.get("GITEE_ACCESS_TOKEN", ""),
            secret=True,
            allow_empty=True,
        )
        updates["GITEE_BASE_URL"] = _prompt_value(
            "GITEE_BASE_URL",
            "Gitee base URL",
            existing_env.get("GITEE_BASE_URL", "https://gitee.com/api/v5"),
            allow_empty=True,
        )

    if _confirm_choice(
        "configure_feishu_service",
        "Configure Feishu service credentials for 'harness server' now?",
        default=bool(existing_env.get("FEISHU_APP_ID") or existing_env.get("FEISHU_APP_SECRET")),
    ):
        updates["FEISHU_APP_ID"] = _prompt_value(
            "FEISHU_APP_ID",
            "Feishu app id",
            existing_env.get("FEISHU_APP_ID", ""),
        )
        updates["FEISHU_APP_SECRET"] = _prompt_value(
            "FEISHU_APP_SECRET",
            "Feishu app secret",
            existing_env.get("FEISHU_APP_SECRET", ""),
            secret=True,
        )

    hitl_mode = _select_option(
        "hitl_mode",
        "Select the human review channel",
        [
            ("stdin", "stdin (local terminal only)"),
            ("email", "email"),
            ("dingtalk", "dingtalk"),
            ("feishu", "feishu"),
        ],
        default=_get_hitl_mode(),
        description="This also updates config/harness.yaml so the runtime matches the generated .env.",
    )
    _save_hitl_mode(hitl_mode)

    if hitl_mode == "email":
        updates.update(_configure_email_hitl(existing_env))
    elif hitl_mode == "dingtalk":
        updates.update(_configure_dingtalk_hitl(existing_env))
    elif hitl_mode == "feishu":
        updates = _configure_feishu_hitl(existing_env, updates)

    _write_env_values(env_path, updates)
    click.echo(f"\n  Configuration saved to {env_path}")
    click.echo(f"  HITL mode saved to {get_config_dir() / 'harness.yaml'}")


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
