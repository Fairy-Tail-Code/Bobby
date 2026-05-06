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


def get_default_runtime_cwd() -> Path:
    """Return the default working directory for MCP tools and agent execution."""
    workspace_dir = get_workspace_dir()
    workspace_dir.mkdir(parents=True, exist_ok=True)
    return workspace_dir.resolve(strict=False)


def get_system_skills_dir() -> Path:
    return get_project_dir() / "skills" / "system"


def get_user_skills_dir() -> Path:
    return get_skills_dir() / "user"


def get_env_path() -> Path:
    return get_home() / ".env"


def get_server_pid_path() -> Path:
    return get_home() / ".server.pid"


def get_server_log_path() -> Path:
    return get_home() / "server.log"


def get_install_marker_path() -> Path:
    return get_home() / ".install-marker"


def get_defaults_dir() -> Path:
    """Return the directory containing default config templates."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "install" / "defaults"
    return get_project_dir() / "install" / "defaults"


def get_agent_prompts_dir() -> Path:
    """Return the directory containing agent prompt markdown files.

    Prompts live under ~/.openharness/agents/prompts/ so they persist
    across PyInstaller temp-directory extractions and are user-editable.
    """
    return get_home() / "agents" / "prompts"


def _get_bundled_prompts_dir() -> Path:
    """Return the prompts directory bundled with the application.

    In PyInstaller mode this is sys._MEIPASS/agents/prompts; in dev
    it is the repo source tree.  Used as the source for initial copy.
    """
    return get_project_dir() / "agents" / "prompts"


def ensure_agent_prompts() -> None:
    """Copy bundled prompts to ~/.openharness/agents/prompts/ if missing."""
    dest_dir = get_agent_prompts_dir()
    src_dir = _get_bundled_prompts_dir()

    if not src_dir.exists():
        return

    dest_dir.mkdir(parents=True, exist_ok=True)

    for md_file in src_dir.glob("*.md"):
        dst = dest_dir / md_file.name
        if not dst.exists():
            dst.write_text(md_file.read_text(encoding="utf-8"), encoding="utf-8")


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
        get_home() / "collected",
    ]:
        d.mkdir(parents=True, exist_ok=True)

    ensure_agent_prompts()
