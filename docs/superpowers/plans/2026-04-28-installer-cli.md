# OpenHarness Installer & CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package OpenHarness as a standalone `harness` CLI tool with cross-platform installer scripts, separating user data into `~/.openharness/`.

**Architecture:** A centralized `infrastructure/paths.py` module resolves all user-data directories to `~/.openharness/` (or `$OPENHARNESS_HOME`). A `cli.py` entry point using click provides all commands. PyInstaller bundles the code + system skills + agent prompts + default config templates into a single executable. Cross-platform installer scripts download the binary and initialize the user directory.

**Tech Stack:** PyInstaller (packaging), click (CLI), PowerShell + Bash (installers), GitHub Actions (CI/CD)

---

## File Structure

### New Files

| File | Responsibility |
|------|----------------|
| `infrastructure/paths.py` | Centralized path resolution (get_home, get_config_dir, etc.) |
| `cli.py` | Click CLI entry point — all `harness` commands |
| `install/defaults/harness.yaml` | Default harness config template for installed mode |
| `install/defaults/mcp.yaml` | Default MCP config (uses `harness _mcp` commands) |
| `install/defaults/skill.yaml` | Default skill assignments |
| `install/defaults/.env.example` | Default env template |
| `install/defaults/user_profile.md` | Empty user profile template |
| `install/install.ps1` | Windows installer script |
| `install/install.sh` | macOS/Linux installer script |
| `harness.spec` | PyInstaller spec file |
| `.github/workflows/release.yml` | CI/CD for 3-platform build + release |

### Modified Files

| File | Change |
|------|--------|
| `config/config.py` | Use `paths.get_home()` / `paths.get_config_dir()` instead of parameter-based resolution |
| `server.py` | Remove `PROJECT_DIR`/`CONFIG_DIR`, use paths module |
| `main.py` | Remove `PROJECT_DIR`/`CONFIG_DIR`, use paths module |
| `agents/factory.py` | `SKILLS_DIR` and config_dir → paths module |
| `infrastructure/session_manager.py` | Default session_dir from paths module |
| `infrastructure/swarm_session.py` | Use paths for snapshot saving |
| `pyproject.toml` | Add `click` and `pyinstaller` dependencies |

---

## Task 1: Create `infrastructure/paths.py`

**Files:**
- Create: `infrastructure/paths.py`

- [ ] **Step 1: Write infrastructure/paths.py**

```python
"""Centralized path resolution for OpenHarness.

All user-data paths resolve to ~/.openharness/ (or $OPENHARNESS_HOME).
Code resources (system skills, agent prompts) resolve to the project directory,
which in PyInstaller mode is sys._MEIPASS.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

VERSION = "1.0.0"


def get_home() -> Path:
    """Return the OpenHarness home directory."""
    return Path(os.environ.get("OPENHARNESS_HOME", str(Path.home() / ".openharness")))


def get_project_dir() -> Path:
    """Return the project root directory.

    In PyInstaller mode, returns sys._MEIPASS.
    In development mode, returns the git repository root (parent of infrastructure/).
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def get_config_dir() -> Path:
    return get_home() / "config"


def get_session_dir() -> Path:
    return get_home() / "session"


def get_memory_dir() -> Path:
    return get_home() / "memory"


def get_skills_dir() -> Path:
    return get_home() / "skills"


def get_workspace_dir() -> Path:
    return get_home() / "workspace"


def get_system_skills_dir() -> Path:
    return get_project_dir() / "skills" / "system"


def get_user_skills_dir() -> Path:
    return get_skills_dir() / "user"


def get_env_path() -> Path:
    return get_home() / ".env"


def get_server_pid_path() -> Path:
    return get_home() / ".server.pid"


def get_install_marker_path() -> Path:
    return get_home() / ".install-marker"


def get_defaults_dir() -> Path:
    """Return the directory containing default config templates."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "install" / "defaults"
    return get_project_dir() / "install" / "defaults"


def get_agent_prompts_dir() -> Path:
    """Return the directory containing agent prompt markdown files."""
    return get_project_dir() / "agents" / "prompts"


def ensure_dirs() -> None:
    """Create all required directories under OPENHARNESS_HOME."""
    for d in [
        get_home(),
        get_home() / "bin",
        get_config_dir(),
        get_session_dir(),
        get_memory_dir(),
        get_skills_dir(),
        get_user_skills_dir(),
        get_workspace_dir(),
        get_workspace_dir() / ".tasks",
        get_home() / ".openharness",
    ]:
        d.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 2: Verify the module loads**

Run: `uv run python -c "from infrastructure.paths import get_home, get_project_dir; print(get_home()); print(get_project_dir())"`
Expected: prints `C:\Users\WUJIEAI\.openharness` and the project root path.

- [ ] **Step 3: Commit**

```bash
git add infrastructure/paths.py
git commit -m "feat: add centralized path resolution module (infrastructure/paths.py)"
```

---

## Task 2: Refactor `config/config.py` to use paths module

**Files:**
- Modify: `config/config.py`

- [ ] **Step 1: Add import and refactor load functions**

Add `from infrastructure.paths import get_home, get_config_dir, get_env_path` at the top.

Change every `load_*_config` function to no longer require `project_dir` / `config_dir` parameters. Instead, they use the paths module directly. The key changes:

```python
# BEFORE (line 163)
def load_llm_config(project_dir: Path) -> LlmConfig:
    env = _load_dotenv(project_dir / ".env")

# AFTER
def load_llm_config() -> LlmConfig:
    env = _load_dotenv(get_env_path())
```

Apply the same pattern to ALL load functions:

```python
def load_mcp_config() -> McpConfig:
    config_dir = get_config_dir()
    mcp_servers = _load_yaml(config_dir / "mcp.yaml")["mcp_servers"]
    base_config = _load_yaml(config_dir / "mcp.yaml")["base_config"]
    servers = []
    for name, cfg in mcp_servers.items():
        servers.append(McpServerConfig(name=name, **cfg))
    return McpConfig(servers=servers, base_config=base_config)


def load_harness_config() -> HarnessConfig:
    config_dir = get_config_dir()
    raw = _load_yaml(config_dir / "harness.yaml")["harness"]
    # ... rest unchanged, just replace ctx_raw references ...
    eval_cfg = raw["evaluation"]
    dimensions = [EvaluationDimension(**d) for d in eval_cfg["dimensions"]]
    ctx_raw = raw.get("context", {})
    context = ContextConfig(
        enabled=ctx_raw.get("enabled", True),
        max_messages=ctx_raw.get("max_messages", 60),
        keep_first_message=ctx_raw.get("keep_first_message", True),
        max_tokens=ctx_raw.get("max_tokens", 80_000),
        auto_compact_enabled=ctx_raw.get("auto_compact_enabled", True),
    )
    hitl_raw = raw.get("hitl", {})
    hitl = HitlConfig(
        mode=hitl_raw.get("mode", "stdin"),
        polling_interval=hitl_raw.get("polling_interval", 30),
        timeout=hitl_raw.get("timeout", 3600),
        subject_prefix=hitl_raw.get("subject_prefix", "[OpenHarness]"),
    )
    return HarnessConfig(
        mode=raw.get("mode", "swarm"),
        max_rounds=ctx_raw["max_rounds"],
        score_threshold=eval_cfg["score_threshold"],
        dimensions=dimensions,
        tech_stack=raw.get("tech_stack", {}),
        context=context,
        hitl=hitl,
        acpx=ClaudeCodeConfig(
            model=acpx_raw.get("model", ""),
            default_timeout=acpx_raw.get("default_timeout", 600),
            max_retries=acpx_raw.get("max_retries", 2),
        ) if (acpx_raw := raw.get("acpx", {})) else ClaudeCodeConfig(),
        knowledge=load_knowledge_config(),
    )


def load_smtp_config() -> SmtpConfig:
    env = _load_dotenv(get_env_path())
    # ... rest unchanged ...


def load_imap_config() -> ImapConfig:
    env = _load_dotenv(get_env_path())
    # ... rest unchanged ...


def load_role_emails() -> dict[str, str]:
    env = _load_dotenv(get_env_path())
    # ... rest unchanged ...


def load_dingtalk_config() -> DingTalkConfig:
    env = _load_dotenv(get_env_path())
    # ... rest unchanged ...


def load_feishu_config() -> FeishuConfig:
    env = _load_dotenv(get_env_path())
    # ... rest unchanged ...


def load_role_dingtalk_ids() -> dict[str, str]:
    env = _load_dotenv(get_env_path())
    # ... rest unchanged ...


def load_role_feishu_open_ids() -> dict[str, str]:
    env = _load_dotenv(get_env_path())
    # ... rest unchanged ...


def load_skill_assignment_config() -> SkillAssignmentConfig:
    config_dir = get_config_dir()
    raw = _load_yaml(config_dir / "skill.yaml")
    return SkillAssignmentConfig(
        skills=raw.get("skills", {}),
        mcp_servers=raw.get("mcp_servers", {}),
    )


def load_knowledge_config() -> KnowledgeConfig:
    """Load knowledge sharing config from .env and harness.yaml."""
    home = get_home()
    env = _load_dotenv(get_env_path())
    config_dir = get_config_dir()
    raw = {}
    if (config_dir / "harness.yaml").exists():
        harness_raw = _load_yaml(config_dir / "harness.yaml")
        raw = harness_raw.get("harness", {}).get("knowledge", {})
    return KnowledgeConfig(
        enabled=raw.get("enabled", False),
        server_url=env.get("KNOWLEDGE_SERVER_URL", raw.get("server_url", "http://localhost:8900")),
        api_key=env.get("KNOWLEDGE_SERVER_API_KEY", ""),
        client_id=env.get("KNOWLEDGE_CLIENT_ID", ""),
        sync_interval_seconds=raw.get("sync_interval_seconds", 300),
        batch_size=raw.get("batch_size", 50),
        max_retries=raw.get("max_retries", 3),
        offline_enabled=raw.get("offline_enabled", True),
        pull_enabled=raw.get("pull_enabled", True),
        pull_categories=raw.get("pull_categories", []),
        local_store_path=str(home / ".openharness" / "knowledge_queue.db"),
        collected_dir=str(home / ".openharness" / "collected"),
    )
```

- [ ] **Step 2: Verify module loads**

Run: `uv run python -c "from config.config import load_llm_config; print('OK')"`
Expected: `OK` (may fail if .env doesn't exist at ~/.openharness — that's fine, we'll handle that in Task 5)

- [ ] **Step 3: Commit**

```bash
git add config/config.py
git commit -m "refactor: config.py uses paths module instead of parameter-based resolution"
```

---

## Task 3: Refactor `server.py` + `main.py` to use paths module

**Files:**
- Modify: `server.py`
- Modify: `main.py`

- [ ] **Step 1: Refactor server.py**

Replace the top-level path definitions and update all references:

```python
# BEFORE (lines 24-25, 35-38, 41-43, 66-68)
PROJECT_DIR = Path(__file__).parent
CONFIG_DIR = PROJECT_DIR / "config"
llm_config = load_llm_config(PROJECT_DIR)
mcp_config = load_mcp_config(CONFIG_DIR)
harness_config = load_harness_config(CONFIG_DIR)
feishu_config = load_feishu_config(PROJECT_DIR)
system_skills_dir = PROJECT_DIR / "skills" / "system"
user_skills_dir = PROJECT_DIR / "skills" / "user"
config_path = CONFIG_DIR / "harness.yaml"
...
session_dir = config_data.get("harness", {}).get("session", {}).get("session_dir", "session")

# AFTER
from infrastructure.paths import (
    get_home, get_config_dir, get_session_dir,
    get_system_skills_dir, get_user_skills_dir,
)

# Remove PROJECT_DIR and CONFIG_DIR entirely.

# In main():
llm_config = load_llm_config()
mcp_config = load_mcp_config()
harness_config = load_harness_config()
feishu_config = load_feishu_config()
system_skills_dir = get_system_skills_dir()
user_skills_dir = get_user_skills_dir()
skill_registry = SkillRegistry(roots=[system_skills_dir, user_skills_dir])

# Replace the session_dir block with:
session_dir = str(get_session_dir())
```

- [ ] **Step 2: Refactor main.py**

```python
# BEFORE (lines 27-28, 30-31, 37-42, 44)
PROJECT_DIR = Path(__file__).parent
CONFIG_DIR = PROJECT_DIR / "config"
config = read_yaml("config/harness.yaml")
session_dir = config.get("harness", {}).get("session", {}).get("session_dir", "session")
llm_config = load_llm_config(PROJECT_DIR)
mcp_config = load_mcp_config(CONFIG_DIR)
harness_config = load_harness_config(CONFIG_DIR)
skill_registry = SkillRegistry(roots=[SKILLS_DIR])

# AFTER
from infrastructure.paths import (
    get_config_dir, get_session_dir, get_system_skills_dir, get_user_skills_dir,
)

# Remove PROJECT_DIR and CONFIG_DIR.

# Replace session setup:
session_dir = str(get_session_dir())
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
session_file = os.path.join(session_dir, f"chat_history_{timestamp}.json")

# In run():
llm_config = load_llm_config()
mcp_config = load_mcp_config()
harness_config = load_harness_config()

system_skills_dir = get_system_skills_dir()
user_skills_dir = get_user_skills_dir()
skill_registry = SkillRegistry(roots=[system_skills_dir, user_skills_dir])

# Update knowledge section (line 173):
# Replace: knowledge_config.collected_dir + "/shared"
# With: str(Path(knowledge_config.collected_dir) / "shared")
```

- [ ] **Step 3: Commit**

```bash
git add server.py main.py
git commit -m "refactor: server.py and main.py use paths module"
```

---

## Task 4: Refactor `agents/factory.py` + `infrastructure/session_manager.py`

**Files:**
- Modify: `agents/factory.py`
- Modify: `infrastructure/session_manager.py`
- Modify: `infrastructure/swarm_session.py`

- [ ] **Step 1: Refactor agents/factory.py**

```python
# BEFORE (line 35, 40)
SKILLS_DIR = Path(__file__).parent.parent / "skills"
config_dir = Path(__file__).parent.parent / "config"

# AFTER
from infrastructure.paths import get_user_skills_dir, get_config_dir, get_system_skills_dir

# Remove SKILLS_DIR entirely.

# In _get_skill_assignment():
config_dir = get_config_dir()

# In create_all_agents() or wherever SkillRegistry is constructed,
# use get_system_skills_dir() + get_user_skills_dir()
# (Note: the callers in server.py/main.py already handle this,
#  but factory.py's SKILLS_DIR export is used by main.py line 19)
```

Since `SKILLS_DIR` is imported by `main.py` (line 19: `from agents.factory import create_all_agents, SKILLS_DIR`), replace that import in main.py with the paths module. In factory.py, remove the `SKILLS_DIR` variable.

- [ ] **Step 2: Refactor infrastructure/session_manager.py**

```python
# BEFORE (line 41)
session_dir: str = "session",

# AFTER
from infrastructure.paths import get_session_dir
session_dir: str = "",  # empty default, resolved in __init__

# In __init__:
if not session_dir:
    session_dir = str(get_session_dir())
self._session_dir = session_dir
```

- [ ] **Step 3: Refactor infrastructure/swarm_session.py**

Check how swarm_session.py uses `session_dir`. If it constructs paths like `Path(self._session_dir) / "snapshot_..."`, they will automatically resolve correctly since `_session_dir` is now an absolute path.

- [ ] **Step 4: Commit**

```bash
git add agents/factory.py infrastructure/session_manager.py infrastructure/swarm_session.py
git commit -m "refactor: factory, session_manager, swarm_session use paths module"
```

---

## Task 5: Add `click` dependency and create `cli.py`

**Files:**
- Modify: `pyproject.toml`
- Create: `cli.py`

- [ ] **Step 1: Add click to pyproject.toml**

Add `"click>=8.1.0"` to the dependencies list in `pyproject.toml`.

- [ ] **Step 2: Install the dependency**

Run: `uv sync`

- [ ] **Step 3: Create cli.py**

```python
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


# ---------------------------------------------------------------------------
# harness run <prompt>
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("prompt", nargs=-1, required=True)
def run(prompt: tuple[str, ...]) -> None:
    """Run a task with the given prompt (CLI mode)."""
    from main import run as _run
    asyncio.run(_run(" ".join(prompt)))


# ---------------------------------------------------------------------------
# harness server start/stop/restart
# ---------------------------------------------------------------------------

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
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=True,
                           capture_output=True)
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
            os.kill(pid, 0)  # Check if process exists
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


# ---------------------------------------------------------------------------
# harness knowledge sync/search/status
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# harness _mcp <name> (hidden — used by installed mcp.yaml)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# harness install
# ---------------------------------------------------------------------------

@cli.command()
def install() -> None:
    """Initialize or repair ~/.openharness/ configuration."""
    home = get_home()
    defaults = get_defaults_dir()

    ensure_dirs()
    click.echo(f"Created directory structure at {home}")

    # Copy default configs (no overwrite)
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

    # Copy .env.example as .env if .env doesn't exist
    env_dst = get_env_path()
    env_src = defaults / ".env.example"
    if not env_dst.exists() and env_src.exists():
        env_dst.write_text(env_src.read_text(encoding="utf-8"), encoding="utf-8")
        click.echo("  Installed .env (from .env.example)")

    # Copy memory template
    profile_dst = get_memory_dir() / "user_profile.md"
    profile_src = defaults / "user_profile.md"
    if not profile_dst.exists() and profile_src.exists():
        profile_dst.write_text(profile_src.read_text(encoding="utf-8"), encoding="utf-8")
        click.echo("  Installed user_profile.md")

    # Write install marker
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


# ---------------------------------------------------------------------------
# harness info
# ---------------------------------------------------------------------------

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
```

- [ ] **Step 4: Verify CLI loads**

Run: `uv run python cli.py --help`
Expected: click help output showing all commands (run, server, knowledge, install, info).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml cli.py
git commit -m "feat: add click CLI entry point with all commands"
```

---

## Task 6: Create default config templates for installed mode

**Files:**
- Create: `install/defaults/harness.yaml`
- Create: `install/defaults/mcp.yaml`
- Create: `install/defaults/skill.yaml`
- Create: `install/defaults/.env.example`
- Create: `install/defaults/user_profile.md`

- [ ] **Step 1: Create install/defaults/ directory and files**

The `harness.yaml` is identical to the current `config/harness.yaml` (it has no path references that change).

The `mcp.yaml` differs from the current `config/mcp.yaml` — it uses `harness _mcp <name>` instead of `uv run python -m ...`:

```yaml
# install/defaults/mcp.yaml
mcp_servers:
  shell:
    transport: stdio
    command: harness
    args: ["_mcp", "shell"]
    startup_timeout: 30

  git:
    transport: stdio
    command: harness
    args: ["_mcp", "git"]
    startup_timeout: 30

  browser:
    transport: stdio
    command: harness
    args: ["_mcp", "browser"]
    startup_timeout: 30

  workspace:
    transport: stdio
    command: harness
    args: ["_mcp", "workspace"]
    startup_timeout: 30

  docker:
    transport: stdio
    command: harness
    args: ["_mcp", "docker"]
    startup_timeout: 30

  database:
    transport: stdio
    command: harness
    args: ["_mcp", "database"]
    startup_timeout: 30

  http_api:
    transport: stdio
    command: harness
    args: ["_mcp", "http_api"]
    startup_timeout: 30

  docs_web:
    transport: stdio
    command: harness
    args: ["_mcp", "docs_web"]
    startup_timeout: 30

  gitee:
    transport: stdio
    command: harness
    args: ["_mcp", "gitee"]
    startup_timeout: 30

  claude_code:
    transport: stdio
    command: harness
    args: ["_mcp", "claude_code"]
    startup_timeout: 10

base_config:
  tool_timeout: 1800
```

Copy `skill.yaml` from current `config/skill.yaml` (unchanged).
Copy `.env.example` from current `.env.example` (unchanged).

Create `user_profile.md`:
```markdown
# User Profile

<!-- This file stores your preferences and profile information. -->
<!-- OpenHarness agents may read this to personalize their interactions. -->
```

- [ ] **Step 2: Commit**

```bash
git add install/defaults/
git commit -m "feat: add default config templates for installed mode"
```

---

## Task 7: Create `install/install.ps1` (Windows installer)

**Files:**
- Create: `install/install.ps1`

- [ ] **Step 1: Write install.ps1**

```powershell
#Requires -Version 5.1
<#
.SYNOPSIS
    OpenHarness installer for Windows.

.DESCRIPTION
    Downloads the harness binary from GitHub Releases and initializes
    the ~/.openharness/ configuration directory.

.EXAMPLE
    irm https://raw.githubusercontent.com/<org>/openharness/main/install/install.ps1 | iex
#>

param(
    [string]$InstallDir = "",
    [string]$Version = "latest",
    [string]$Channel = "irm-install"
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

$script:RepoOwner = "openharness"
$script:RepoName = "openharness"
$script:HasGit = $false
$script:HasPython = $false
$script:HasUv = $false

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Write-Banner {
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║       OpenHarness Installer          ║" -ForegroundColor Cyan
    Write-Host "  ╚══════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Ok($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "  [ERROR] $msg" -ForegroundColor Red }

function Get-HarnessHome {
    if ($script:InstallDir) { return $script:InstallDir }
    $envHome = [Environment]::GetEnvironmentVariable("OPENHARNESS_HOME", "User")
    if ($envHome) { return $envHome }
    return Join-Path $env:USERPROFILE ".openharness"
}

function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "Machine")
}

# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------

function Test-Python {
    Refresh-Path
    try {
        $py = Get-Command python -ErrorAction SilentlyContinue
        if (-not $py) { $py = Get-Command python3 -ErrorAction SilentlyContinue }
        if ($py) {
            $ver = & $py.Source --version 2>&1
            Write-Ok "Python found: $ver"
            $script:HasPython = $true
            return $true
        }
    } catch {}
    Write-Warn "Python not found. Required for MCP servers."
    return $false
}

function Install-Uv {
    Refresh-Path
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-Ok "uv found: $(uv --version)"
        $script:HasUv = $true
        return $true
    }
    Write-Host "  Installing uv..."
    try {
        winget install astral-sh.uv --accept-source-agreements --accept-package-agreements 2>$null
        Refresh-Path
        if (Get-Command uv -ErrorAction SilentlyContinue) {
            Write-Ok "uv installed via winget"
            $script:HasUv = $true
            return $true
        }
    } catch {}
    try {
        $installScript = Invoke-RestMethod https://astral.sh/uv/install.ps1
        Invoke-Expression $installScript
        Refresh-Path
        if (Get-Command uv -ErrorAction SilentlyContinue) {
            Write-Ok "uv installed via install script"
            $script:HasUv = $true
            return $true
        }
    } catch {}
    Write-Warn "Could not install uv. Install manually: winget install astral-sh.uv"
    return $false
}

function Test-Git {
    Refresh-Path
    if (Get-Command git -ErrorAction SilentlyContinue) {
        $script:HasGit = $true
        Write-Ok "Git found: $(git --version)"
        return $true
    }
    Write-Warn "Git not found. Required for some features."
    return $false
}

# ---------------------------------------------------------------------------
# Install functions
# ---------------------------------------------------------------------------

function Initialize-DirectoryStructure {
    param([string]$Home)

    $dirs = @(
        $Home,
        Join-Path $Home "bin",
        Join-Path $Home "config",
        Join-Path $Home "session",
        Join-Path $Home "memory",
        Join-Path $Home "skills\user",
        Join-Path $Home "workspace\.tasks",
        Join-Path $Home ".openharness"
    )
    foreach ($dir in $dirs) {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
    }
    Write-Ok "Directory structure created at $Home"
}

function Install-HarnessBinary {
    param([string]$Home, [string]$Version)

    $binDir = Join-Path $Home "bin"
    $dest = Join-Path $binDir "harness.exe"

    if (Test-Path $dest) {
        Write-Ok "harness.exe already exists, skipping download"
        return $true
    }

    # Determine download URL
    $tag = if ($Version -eq "latest") { "latest" } else { "v$Version" }
    $baseUrl = "https://github.com/$script:RepoOwner/$script:RepoName/releases/$tag/download"
    $url = "$baseUrl/harness-windows.exe"

    Write-Host "  Downloading harness binary..."
    try {
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
        Write-Ok "Downloaded harness.exe to $dest"
        return $true
    } catch {
        # Fallback: try building from source if Python + uv available
        if ($script:HasPython -and $script:HasUv) {
            Write-Warn "Download failed. Attempting to build from source..."
            return Build-FromSource -Home $Home
        }
        Write-Err "Download failed and cannot build from source: $_"
        return $false
    }
}

function Build-FromSource {
    param([string]$Home)

    $binDir = Join-Path $Home "bin"
    $dest = Join-Path $binDir "harness.exe"

    Write-Host "  Building harness from source..."

    # Clone or use existing
    $repoDir = Join-Path $Home "repo"
    if (-not (Test-Path $repoDir)) {
        git clone "https://github.com/$script:RepoOwner/$script:RepoName.git" $repoDir
    }

    Push-Location $repoDir
    try {
        uv sync
        uv run pyinstaller cli.py --onefile --name harness --distpath $binDir
        if (Test-Path $dest) {
            Write-Ok "Built harness.exe from source"
            return $true
        }
        Write-Err "Build failed"
        return $false
    } finally {
        Pop-Location
    }
}

function Initialize-DefaultConfigs {
    param([string]$Home)

    $configDir = Join-Path $Home "config"
    $defaultsDir = Join-Path $PSScriptRoot "defaults"

    # If defaults dir doesn't exist (running via irm), download them
    if (-not (Test-Path $defaultsDir)) {
        $defaultsDir = Join-Path $Home "defaults_temp"
        New-Item -ItemType Directory -Path $defaultsDir -Force | Out-Null
        $baseUrl = "https://raw.githubusercontent.com/$script:RepoOwner/$script:RepoName/main/install/defaults"
        foreach ($file in @("harness.yaml", "mcp.yaml", "skill.yaml", ".env.example", "user_profile.md")) {
            try {
                Invoke-WebRequest -Uri "$baseUrl/$file" -OutFile (Join-Path $defaultsDir $file) -UseBasicParsing
            } catch {
                Write-Warn "Could not download default config: $file"
            }
        }
    }

    foreach ($file in @("harness.yaml", "mcp.yaml", "skill.yaml", ".env.example")) {
        $src = Join-Path $defaultsDir $file
        $dst = Join-Path $configDir $file
        if (Test-Path $dst) {
            Write-Host "  Skipped $file (already exists)"
        } elseif (Test-Path $src) {
            Copy-Item $src $dst
            Write-Ok "Installed $file"
        }
    }

    # Copy .env.example as .env
    $envDst = Join-Path $Home ".env"
    $envSrc = Join-Path $defaultsDir ".env.example"
    if (-not (Test-Path $envDst) -and (Test-Path $envSrc)) {
        Copy-Item $envSrc $envDst
        Write-Ok "Installed .env"
    }

    # Copy user_profile.md
    $profileDst = Join-Path $Home "memory\user_profile.md"
    $profileSrc = Join-Path $defaultsDir "user_profile.md"
    if (-not (Test-Path $profileDst) -and (Test-Path $profileSrc)) {
        Copy-Item $profileSrc $profileDst
        Write-Ok "Installed user_profile.md"
    }

    # Write install marker
    $markerPath = Join-Path $Home ".install-marker"
    if (-not (Test-Path $markerPath)) {
        $marker = @{
            version = "1.0.0"
            installed_at = (Get-Date).ToUniversalTime().ToString("o")
            platform = "windows"
            channel = $script:Channel
        }
        $marker | ConvertTo-Json | Set-Content $markerPath
        Write-Ok "Wrote install marker"
    }
}

function Set-PathVariable {
    param([string]$Home)

    $binDir = Join-Path $Home "bin"
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -split ";" | Where-Object { $_ -eq $binDir }) {
        Write-Ok "PATH already contains $binDir"
        return
    }
    $newPath = "$userPath;$binDir"
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Refresh-Path
    Write-Ok "Added $binDir to user PATH"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

function Main {
    Write-Banner

    $home = Get-HarnessHome
    Write-Host "  Install directory: $home" -ForegroundColor White
    Write-Host ""

    # Dependency checks
    Test-Python | Out-Null
    Install-Uv | Out-Null
    Test-Git | Out-Null
    Write-Host ""

    # Install
    Initialize-DirectoryStructure $home
    Install-HarnessBinary $home $Version
    Initialize-DefaultConfigs $home
    Set-PathVariable $home

    # Summary
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "  ║     Installation Complete!            ║" -ForegroundColor Green
    Write-Host "  ╚══════════════════════════════════════╝" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Binary:  $home\bin\harness.exe" -ForegroundColor White
    Write-Host "  Config:  $home\config\" -ForegroundColor White
    Write-Host "  .env:    $home\.env" -ForegroundColor White
    Write-Host ""
    Write-Host "  Next steps:" -ForegroundColor Yellow
    Write-Host "    1. Edit $home\.env with your API keys"
    Write-Host "    2. Open a new terminal (to refresh PATH)"
    Write-Host "    3. Run: harness info"

    if (-not $script:HasPython) {
        Write-Host ""
        Write-Warn "Python not found. MCP servers require Python."
        Write-Host "  Install: winget install Python.Python.3.12"
    }
}

try {
    Main
} catch {
    Write-Err "Installation failed: $_"
    exit 1
}
```

- [ ] **Step 2: Commit**

```bash
git add install/install.ps1
git commit -m "feat: add Windows installer script (install.ps1)"
```

---

## Task 8: Create `install/install.sh` (macOS/Linux installer)

**Files:**
- Create: `install/install.sh`

- [ ] **Step 1: Write install.sh**

```bash
#!/usr/bin/env bash
#
# OpenHarness installer for macOS and Linux.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/<org>/openharness/main/install/install.sh | bash
#
set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
REPO_OWNER="openharness"
REPO_NAME="openharness"
VERSION="${INSTALL_VERSION:-latest}"
CHANNEL="${INSTALL_CHANNEL:-curl-install}"
HAS_PYTHON=false
HAS_UV=false
HAS_GIT=false

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()    { echo -e "${CYAN}  [INFO]${NC} $*"; }
ok()      { echo -e "${GREEN}  [OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}  [WARN]${NC} $*"; }
err()     { echo -e "${RED}  [ERROR]${NC} $*"; }

banner() {
    echo ""
    echo -e "  ${CYAN}╔══════════════════════════════════════╗${NC}"
    echo -e "  ${CYAN}║       OpenHarness Installer          ║${NC}"
    echo -e "  ${CYAN}╚══════════════════════════════════════╝${NC}"
    echo ""
}

get_harness_home() {
    if [[ -n "${OPENHARNESS_HOME:-}" ]]; then
        echo "$OPENHARNESS_HOME"
    else
        echo "$HOME/.openharness"
    fi
}

refresh_path() {
    export PATH="$(bash -l -c 'echo $PATH' 2>/dev/null || echo $PATH)"
}

# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------
check_python() {
    refresh_path
    if command -v python3 &>/dev/null; then
        local ver
        ver=$(python3 --version 2>&1)
        ok "Python found: $ver"
        HAS_PYTHON=true
        return 0
    elif command -v python &>/dev/null; then
        local ver
        ver=$(python --version 2>&1)
        ok "Python found: $ver"
        HAS_PYTHON=true
        return 0
    fi
    warn "Python not found. MCP servers require Python."
    return 1
}

install_uv() {
    refresh_path
    if command -v uv &>/dev/null; then
        ok "uv found: $(uv --version)"
        HAS_UV=true
        return 0
    fi
    info "Installing uv..."
    # Try brew first (macOS)
    if [[ "$(uname)" == "Darwin" ]] && command -v brew &>/dev/null; then
        brew install uv 2>/dev/null && refresh_path && command -v uv &>/dev/null && {
            ok "uv installed via brew"
            HAS_UV=true
            return 0
        }
    fi
    # Try pip
    pip install uv 2>/dev/null && refresh_path && command -v uv &>/dev/null && {
        ok "uv installed via pip"
        HAS_UV=true
        return 0
    }
    # Try official installer
    curl -fsSL https://astral.sh/uv/install.sh | sh 2>/dev/null && refresh_path && command -v uv &>/dev/null && {
        ok "uv installed via official script"
        HAS_UV=true
        return 0
    }
    warn "Could not install uv. Install manually: curl -fsSL https://astral.sh/uv/install.sh | sh"
    return 1
}

check_git() {
    if command -v git &>/dev/null; then
        ok "Git found: $(git --version)"
        HAS_GIT=true
        return 0
    fi
    warn "Git not found. Required for some features."
    return 1
}

# ---------------------------------------------------------------------------
# Install functions
# ---------------------------------------------------------------------------
init_directory_structure() {
    local home="$1"
    local dirs=(
        "$home"
        "$home/bin"
        "$home/config"
        "$home/session"
        "$home/memory"
        "$home/skills/user"
        "$home/workspace/.tasks"
        "$home/.openharness"
    )
    for dir in "${dirs[@]}"; do
        mkdir -p "$dir"
    done
    ok "Directory structure created at $home"
}

install_harness_binary() {
    local home="$1"
    local dest="$home/bin/harness"

    if [[ -f "$dest" ]]; then
        ok "harness binary already exists, skipping download"
        return 0
    fi

    local tag
    tag=$( [[ "$VERSION" == "latest" ]] && echo "latest" || echo "v$VERSION" )
    local os_name arch
    os_name=$(uname -s | tr '[:upper:]' '[:lower:]')
    case "$(uname -m)" in
        x86_64|amd64) arch="x86_64" ;;
        arm64|aarch64) arch="aarch64" ;;
        *) arch="$(uname -m)" ;;
    esac

    local url="https://github.com/$REPO_OWNER/$REPO_NAME/releases/$tag/download/harness-${os_name}-${arch}"

    info "Downloading harness binary..."
    if curl -fsSL -o "$dest" "$url"; then
        chmod +x "$dest"
        ok "Downloaded harness to $dest"
        return 0
    fi

    # Fallback: try generic name
    url="https://github.com/$REPO_OWNER/$REPO_NAME/releases/$tag/download/harness"
    if curl -fsSL -o "$dest" "$url"; then
        chmod +x "$dest"
        ok "Downloaded harness to $dest"
        return 0
    fi

    # Fallback: build from source
    if $HAS_PYTHON && $HAS_UV; then
        warn "Download failed. Attempting to build from source..."
        build_from_source "$home"
        return $?
    fi

    err "Download failed and cannot build from source."
    return 1
}

build_from_source() {
    local home="$1"
    local dest="$home/bin/harness"

    info "Building harness from source..."
    local repo_dir="$home/repo"
    if [[ ! -d "$repo_dir" ]]; then
        git clone "https://github.com/$REPO_OWNER/$REPO_NAME.git" "$repo_dir"
    fi
    cd "$repo_dir"
    uv sync
    uv run pyinstaller cli.py --onefile --name harness --distpath "$home/bin"
    if [[ -f "$dest" ]]; then
        ok "Built harness from source"
        return 0
    fi
    err "Build failed"
    return 1
}

init_default_configs() {
    local home="$1"
    local config_dir="$home/config"
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local defaults_dir="$script_dir/defaults"

    # If defaults dir doesn't exist (running via curl), download them
    if [[ ! -d "$defaults_dir" ]]; then
        defaults_dir="$home/defaults_temp"
        mkdir -p "$defaults_dir"
        local base_url="https://raw.githubusercontent.com/$REPO_OWNER/$REPO_NAME/main/install/defaults"
        for file in harness.yaml mcp.yaml skill.yaml .env.example user_profile.md; do
            curl -fsSL -o "$defaults_dir/$file" "$base_url/$file" 2>/dev/null || \
                warn "Could not download default config: $file"
        done
    fi

    for file in harness.yaml mcp.yaml skill.yaml .env.example; do
        local src="$defaults_dir/$file"
        local dst="$config_dir/$file"
        if [[ -f "$dst" ]]; then
            echo "  Skipped $file (already exists)"
        elif [[ -f "$src" ]]; then
            cp "$src" "$dst"
            ok "Installed $file"
        fi
    done

    # Copy .env.example as .env
    local env_dst="$home/.env"
    local env_src="$defaults_dir/.env.example"
    if [[ ! -f "$env_dst" ]] && [[ -f "$env_src" ]]; then
        cp "$env_src" "$env_dst"
        ok "Installed .env"
    fi

    # Copy user_profile.md
    local profile_dst="$home/memory/user_profile.md"
    local profile_src="$defaults_dir/user_profile.md"
    if [[ ! -f "$profile_dst" ]] && [[ -f "$profile_src" ]]; then
        cp "$profile_src" "$profile_dst"
        ok "Installed user_profile.md"
    fi

    # Write install marker
    local marker_path="$home/.install-marker"
    if [[ ! -f "$marker_path" ]]; then
        cat > "$marker_path" <<MARKER_EOF
{
  "version": "1.0.0",
  "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "platform": "$(uname -s)",
  "channel": "$CHANNEL"
}
MARKER_EOF
        ok "Wrote install marker"
    fi
}

set_path_variable() {
    local home="$1"
    local bin_dir="$home/bin"

    # Check if already in PATH
    if echo "$PATH" | tr ':' '\n' | grep -qF "$bin_dir"; then
        ok "PATH already contains $bin_dir"
        return 0
    fi

    # Detect shell and add to appropriate rc file
    local rc_file=""
    local shell_name="$(basename "${SHELL:-bash}")"
    case "$shell_name" in
        zsh)  rc_file="$HOME/.zshrc" ;;
        bash) rc_file="$HOME/.bashrc" ;;
        *)    rc_file="$HOME/.profile" ;;
    esac

    echo "" >> "$rc_file"
    echo "# OpenHarness" >> "$rc_file"
    echo "export PATH=\"\$PATH:$bin_dir\"" >> "$rc_file"
    export PATH="$PATH:$bin_dir"
    ok "Added $bin_dir to PATH (via $rc_file)"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    banner

    local home
    home="$(get_harness_home)"
    echo "  Install directory: $home"
    echo ""

    # Dependency checks
    check_python || true
    install_uv || true
    check_git || true
    echo ""

    # Install
    init_directory_structure "$home"
    install_harness_binary "$home"
    init_default_configs "$home"
    set_path_variable "$home"

    # Summary
    echo ""
    echo -e "  ${GREEN}╔══════════════════════════════════════╗${NC}"
    echo -e "  ${GREEN}║     Installation Complete!            ║${NC}"
    echo -e "  ${GREEN}╚══════════════════════════════════════╝${NC}"
    echo ""
    echo "  Binary:  $home/bin/harness"
    echo "  Config:  $home/config/"
    echo "  .env:    $home/.env"
    echo ""
    echo -e "  ${YELLOW}Next steps:${NC}"
    echo "    1. Edit $home/.env with your API keys"
    echo "    2. Run: source ~/.bashrc  (or restart your shell)"
    echo "    3. Run: harness info"

    if ! $HAS_PYTHON; then
        echo ""
        warn "Python not found. MCP servers require Python."
        echo "  Install: https://www.python.org/downloads/"
    fi
}

trap 'err "Installation failed on line $LINENO"; exit 1' ERR
main
```

- [ ] **Step 2: Make executable and commit**

```bash
chmod +x install/install.sh
git add install/install.sh
git commit -m "feat: add macOS/Linux installer script (install.sh)"
```

---

## Task 9: Create PyInstaller spec and GitHub Actions release workflow

**Files:**
- Create: `harness.spec`
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Create harness.spec**

```python
# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for OpenHarness CLI."""

import sys
from pathlib import Path

block_cipher = None

PROJECT = Path('.')

# Data files to bundle
datas = [
    # System skills (20 skill directories with SKILL.md files)
    (str(PROJECT / 'skills' / 'system'), 'skills/system'),
    # Agent prompts
    (str(PROJECT / 'agents' / 'prompts'), 'agents/prompts'),
    # Default config templates for 'harness install'
    (str(PROJECT / 'install' / 'defaults'), 'install/defaults'),
]

a = Analysis(
    ['cli.py'],
    pathex=[str(PROJECT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'infrastructure.paths',
        'infrastructure.mcp_servers.shell_server',
        'infrastructure.mcp_servers.git_server',
        'infrastructure.mcp_servers.browser_server',
        'infrastructure.mcp_servers.workspace_server',
        'infrastructure.mcp_servers.docker_server',
        'infrastructure.mcp_servers.database_server',
        'infrastructure.mcp_servers.http_api_server',
        'infrastructure.mcp_servers.docs_web_server',
        'infrastructure.mcp_servers.gitee_server',
        'infrastructure.mcp_servers.claude_code_server',
        'infrastructure.mcp.manager',
        'infrastructure.mcp.tool_bridge',
        'infrastructure.skills.registry',
        'infrastructure.skills.tool',
        'infrastructure.skills.skill_inject',
        'infrastructure.session_manager',
        'infrastructure.swarm_session',
        'infrastructure.context.auto_compact',
        'infrastructure.context.snip',
        'infrastructure.feishu_bot',
        'infrastructure.channel.channel_feishu_service',
        'agents.factory',
        'agents.planner',
        'agents.generator',
        'agents.evaluator',
        'agents.PM',
        'agents.single',
        'agents.user',
        'agents.channel_proxy',
        'config.config',
        'orchestration.group',
        'utils.yaml_reader',
        'mcp',
        'mcp.server',
        'mcp.server.fastmcp',
        'mcp.types',
        'autogen',
        'click',
        'yaml',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy.testing'],
    noarchive=False,
    optimize=0,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='harness',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

- [ ] **Step 2: Create .github/workflows/release.yml**

```yaml
name: Build & Release

on:
  push:
    tags: ['v*']
  workflow_dispatch:
    inputs:
      version:
        description: 'Version tag (e.g. v1.0.0)'
        required: true

permissions:
  contents: write

jobs:
  build:
    strategy:
      fail-fast: false
      matrix:
        include:
          - os: windows-latest
            artifact: harness.exe
            platform: windows
          - os: macos-latest
            artifact: harness
            platform: macos
          - os: ubuntu-latest
            artifact: harness
            platform: linux

    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Set up Python
        run: uv python install 3.12

      - name: Install dependencies
        run: uv sync

      - name: Build with PyInstaller
        run: uv run pyinstaller harness.spec

      - name: Rename binary with platform suffix
        shell: bash
        run: |
          cd dist
          if [ "${{ matrix.platform }}" = "windows" ]; then
            mv harness.exe harness-windows.exe
          elif [ "${{ matrix.platform }}" = "macos" ]; then
            mv harness harness-macos
          else
            mv harness harness-linux
          fi

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: harness-${{ matrix.platform }}
          path: dist/harness-*

  release:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Download all artifacts
        uses: actions/download-artifact@v4
        with:
          path: artifacts

      - name: Create release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ github.event.inputs.version || github.ref_name }}
          files: artifacts/**/*
          generate_release_notes: true
```

- [ ] **Step 3: Commit**

```bash
git add harness.spec .github/workflows/release.yml
git commit -m "feat: add PyInstaller spec and GitHub Actions release workflow"
```

---

## Task 10: Smoke test — verify dev mode still works

**Files:** None (verification only)

- [ ] **Step 1: Run harness install to set up ~/.openharness/**

Run: `uv run python cli.py install`
Expected: Directory structure created, default configs installed, no errors.

- [ ] **Step 2: Copy .env with real keys**

Copy your existing `.env` to `~/.openharness/.env`.

- [ ] **Step 3: Verify harness info**

Run: `uv run python cli.py info`
Expected: Shows correct paths, version, install marker.

- [ ] **Step 4: Verify harness --help**

Run: `uv run python cli.py --help`
Expected: Help output showing all commands.

- [ ] **Step 5: Verify server module loads**

Run: `uv run python -c "from server import main; print('server OK')"`
Expected: `server OK`

- [ ] **Step 6: Verify main module loads**

Run: `uv run python -c "from main import run; print('main OK')"`
Expected: `main OK`

---

## Self-Review

**1. Spec coverage:**
- Directory layout → Task 1 (paths.py), Task 6 (defaults)
- Path resolution → Task 1
- CLI commands → Task 5 (all commands)
- Code refactoring → Tasks 2-4
- install.ps1 → Task 7
- install.sh → Task 8
- PyInstaller → Task 9
- GitHub Actions → Task 9
- No-overwrite policy → Task 5 (install command), Tasks 7-8 (installers)
- irm/curl install → Tasks 7-8

**2. Placeholder scan:** No TBD/TODO found. All code is complete.

**3. Type consistency:**
- `get_home()` returns `Path` — used consistently
- `load_*_config()` functions now take no arguments — callers updated in Tasks 3-4
- `session_dir` is `str` — `get_session_dir()` returns `Path`, converted with `str()`
- `_MCP_SERVERS` dict maps string→string — `_make_mcp_command` closure correctly captures module path
- `VERSION` defined in `paths.py` and imported by `cli.py` — single source of truth
