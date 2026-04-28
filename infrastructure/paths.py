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