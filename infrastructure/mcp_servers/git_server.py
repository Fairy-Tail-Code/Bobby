from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations


git_server = FastMCP("openharness-git", log_level="ERROR")


def build_git_server() -> FastMCP:
    """Return the configured git MCP server instance."""
    return git_server


@git_server.tool(
    description="Return git status for one repository.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def get_git_status(repo_path: str = ".", cwd: str | None = None) -> dict[str, Any]:
    """Return concise git status metadata."""
    repo_root = _resolve_git_repo_root(repo_path, cwd=cwd)
    branch = _run_git_command(repo_root, ["branch", "--show-current"]).stdout.strip()
    porcelain = _run_git_command(repo_root, ["status", "--short"]).stdout.splitlines()
    return {
        "ok": True,
        "repo_path": str(repo_root),
        "branch": branch or None,
        "entries": [_parse_status_entry(line) for line in porcelain if line.strip()],
        "is_clean": not porcelain,
    }


@git_server.tool(
    description="Return the current worktree diff for one repository.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def inspect_git_diff(
    repo_path: str = ".",
    cwd: str | None = None,
    pathspecs: list[str] | None = None,
) -> dict[str, Any]:
    """Return the unstaged worktree diff."""
    repo_root = _resolve_git_repo_root(repo_path, cwd=cwd)
    command = ["diff", "--"]
    normalized_pathspecs = _normalize_pathspecs(pathspecs)
    if normalized_pathspecs:
        command.extend(normalized_pathspecs)
    diff_text = _run_git_command(repo_root, command).stdout
    return {
        "ok": True,
        "repo_path": str(repo_root),
        "pathspecs": list(normalized_pathspecs),
        "diff": diff_text,
    }


@git_server.tool(
    description="Return the staged diff for one repository.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def inspect_git_staged_diff(
    repo_path: str = ".",
    cwd: str | None = None,
    pathspecs: list[str] | None = None,
) -> dict[str, Any]:
    """Return the staged diff."""
    repo_root = _resolve_git_repo_root(repo_path, cwd=cwd)
    command = ["diff", "--cached", "--"]
    normalized_pathspecs = _normalize_pathspecs(pathspecs)
    if normalized_pathspecs:
        command.extend(normalized_pathspecs)
    diff_text = _run_git_command(repo_root, command).stdout
    return {
        "ok": True,
        "repo_path": str(repo_root),
        "pathspecs": list(normalized_pathspecs),
        "diff": diff_text,
    }


@git_server.tool(
    description="List local and remote branches for one repository.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def list_git_branches(repo_path: str = ".", cwd: str | None = None) -> dict[str, Any]:
    """List branches for one repository."""
    repo_root = _resolve_git_repo_root(repo_path, cwd=cwd)
    branch_lines = _run_git_command(repo_root, ["branch", "-a", "--no-color"]).stdout.splitlines()
    branches = []
    current_branch: str | None = None
    for line in branch_lines:
        normalized_line = line.strip()
        if not normalized_line:
            continue
        is_current = normalized_line.startswith("*")
        branch_name = normalized_line[2:].strip() if is_current else normalized_line
        if is_current:
            current_branch = branch_name
        branches.append(
            {
                "name": branch_name,
                "current": is_current,
                "remote": branch_name.startswith("remotes/"),
            }
        )
    return {
        "ok": True,
        "repo_path": str(repo_root),
        "current_branch": current_branch,
        "branches": branches,
    }


@git_server.tool(
    description="Return recent commit metadata for one repository.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def inspect_git_log(
    repo_path: str = ".",
    cwd: str | None = None,
    max_count: int = 20,
) -> dict[str, Any]:
    """Return recent commit history."""
    repo_root = _resolve_git_repo_root(repo_path, cwd=cwd)
    if max_count <= 0:
        raise ValueError("Tool field 'max_count' must be a positive integer.")
    log_output = _run_git_command(
        repo_root,
        [
            "log",
            f"--max-count={max_count}",
            "--date=iso-strict",
            "--pretty=format:%H%x1f%an%x1f%ae%x1f%ad%x1f%s",
        ],
    ).stdout
    commits = []
    for line in log_output.splitlines():
        if not line.strip():
            continue
        commit_hash, author_name, author_email, authored_at, subject = line.split("\x1f", maxsplit=4)
        commits.append(
            {
                "hash": commit_hash,
                "author_name": author_name,
                "author_email": author_email,
                "authored_at": authored_at,
                "subject": subject,
            }
        )
    return {
        "ok": True,
        "repo_path": str(repo_root),
        "commits": commits,
    }


@git_server.tool(
    description="Show one commit with metadata and patch text.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def show_git_commit(
    commit: str = "HEAD",
    repo_path: str = ".",
    cwd: str | None = None,
) -> dict[str, Any]:
    """Return metadata and patch text for one commit."""
    repo_root = _resolve_git_repo_root(repo_path, cwd=cwd)
    normalized_commit = _normalize_required_string(commit, field_name="commit")
    metadata = _run_git_command(
        repo_root,
        [
            "show",
            "--quiet",
            "--date=iso-strict",
            "--pretty=format:%H%x1f%an%x1f%ae%x1f%ad%x1f%s",
            normalized_commit,
        ],
    ).stdout.strip()
    patch_text = _run_git_command(repo_root, ["show", "--format=", normalized_commit]).stdout
    commit_hash, author_name, author_email, authored_at, subject = metadata.split("\x1f", maxsplit=4)
    return {
        "ok": True,
        "repo_path": str(repo_root),
        "commit": {
            "hash": commit_hash,
            "author_name": author_name,
            "author_email": author_email,
            "authored_at": authored_at,
            "subject": subject,
        },
        "patch": patch_text,
    }


@git_server.tool(
    description="Create one new local branch in a repository.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False),
)
def create_git_branch(
    branch_name: str,
    repo_path: str = ".",
    cwd: str | None = None,
    checkout: bool = False,
    start_point: str | None = None,
) -> dict[str, Any]:
    """Create one branch and optionally check it out."""
    repo_root = _resolve_git_repo_root(repo_path, cwd=cwd)
    normalized_branch_name = _normalize_required_string(branch_name, field_name="branch_name")
    command = ["switch", "-c", normalized_branch_name]
    if not checkout:
        command = ["branch", normalized_branch_name]
    if isinstance(start_point, str) and start_point.strip():
        command.append(start_point.strip())
    _run_git_command(repo_root, command)
    current_branch = _run_git_command(repo_root, ["branch", "--show-current"]).stdout.strip()
    return {
        "ok": True,
        "repo_path": str(repo_root),
        "branch_name": normalized_branch_name,
        "checked_out": checkout,
        "current_branch": current_branch or None,
    }


@git_server.tool(
    description="Stage one or more paths in a repository.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False),
)
def stage_git_paths(
    paths: list[str],
    repo_path: str = ".",
    cwd: str | None = None,
) -> dict[str, Any]:
    """Stage one or more paths."""
    repo_root = _resolve_git_repo_root(repo_path, cwd=cwd)
    normalized_paths = _normalize_pathspecs(paths, field_name="paths")
    if not normalized_paths:
        raise ValueError("Tool field 'paths' must contain at least one path.")
    _run_git_command(repo_root, ["add", "--", *normalized_paths])
    staged_entries = _run_git_command(repo_root, ["diff", "--cached", "--name-only", "--", *normalized_paths]).stdout
    return {
        "ok": True,
        "repo_path": str(repo_root),
        "paths": list(normalized_paths),
        "staged_paths": [line.strip() for line in staged_entries.splitlines() if line.strip()],
    }


@git_server.tool(
    description="Create one local commit from staged changes.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False),
)
def commit_git_changes(
    message: str,
    repo_path: str = ".",
    cwd: str | None = None,
    author_name: str | None = None,
    author_email: str | None = None,
) -> dict[str, Any]:
    """Create one commit from staged changes."""
    repo_root = _resolve_git_repo_root(repo_path, cwd=cwd)
    normalized_message = _normalize_required_string(message, field_name="message")
    command = ["commit", "-m", normalized_message]
    if (author_name is None) ^ (author_email is None):
        raise ValueError("Tools fields 'author_name' and 'author_email' must be provided together.")
    if author_name is not None and author_email is not None:
        normalized_author_name = _normalize_required_string(author_name, field_name="author_name")
        normalized_author_email = _normalize_required_string(author_email, field_name="author_email")
        command.extend(["--author", f"{normalized_author_name} <{normalized_author_email}>"])
    _run_git_command(repo_root, command)
    head_metadata = _run_git_command(
        repo_root,
        [
            "show",
            "--quiet",
            "--date=iso-strict",
            "--pretty=format:%H%x1f%an%x1f%ae%x1f%ad%x1f%s",
            "HEAD",
        ],
    ).stdout.strip()
    commit_hash, commit_author_name, commit_author_email, authored_at, subject = head_metadata.split(
        "\x1f",
        maxsplit=4,
    )
    return {
        "ok": True,
        "repo_path": str(repo_root),
        "commit": {
            "hash": commit_hash,
            "author_name": commit_author_name,
            "author_email": commit_author_email,
            "authored_at": authored_at,
            "subject": subject,
        },
    }


@git_server.tool(
    description="Clone one git repository to a destination path.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False),
)
def clone_git_repository(
    repo_url: str,
    destination_path: str,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Clone one remote repository into a destination directory."""
    normalized_repo_url = _normalize_required_string(repo_url, field_name="repo_url")
    root = Path.cwd().resolve() if cwd is None else Path(cwd).expanduser().resolve(strict=False)
    destination = Path(destination_path).expanduser()
    if not destination.is_absolute():
        destination = root / destination
    destination = destination.resolve(strict=False)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError(f"Destination path '{destination}' already exists and is not empty.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    completed_process = subprocess.run(
        ["git", "clone", normalized_repo_url, str(destination)],
        text=True,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        env=_git_env(),
        timeout=300,
    )
    if completed_process.returncode != 0:
        stderr = completed_process.stderr.strip() or completed_process.stdout.strip()
        raise ValueError(stderr or f"Git command failed: git clone {normalized_repo_url} {destination}")
    return {
        "ok": True,
        "repo_url": normalized_repo_url,
        "repo_path": str(destination),
    }


@git_server.tool(
    description="Fetch refs from one repository remote.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False),
)
def fetch_git_remote(
    repo_path: str = ".",
    cwd: str | None = None,
    remote: str = "origin",
) -> dict[str, Any]:
    """Fetch the requested remote."""
    repo_root = _resolve_git_repo_root(repo_path, cwd=cwd)
    normalized_remote = _normalize_required_string(remote, field_name="remote")
    _run_git_command(repo_root, ["fetch", normalized_remote])
    return {
        "ok": True,
        "repo_path": str(repo_root),
        "remote": normalized_remote,
    }


@git_server.tool(
    description="Switch to one local or remote-tracking branch in a repository.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False),
)
def checkout_git_branch(
    branch_name: str,
    repo_path: str = ".",
    cwd: str | None = None,
    create: bool = False,
    start_point: str | None = None,
    track_remote: bool = False,
) -> dict[str, Any]:
    """Check out one branch in the repository."""
    repo_root = _resolve_git_repo_root(repo_path, cwd=cwd)
    normalized_branch_name = _normalize_required_string(branch_name, field_name="branch_name")
    if create:
        command = ["switch", "-c", normalized_branch_name]
        if isinstance(start_point, str) and start_point.strip():
            command.append(start_point.strip())
    elif track_remote:
        command = ["switch", "--track", "-C", normalized_branch_name, f"origin/{normalized_branch_name}"]
    else:
        command = ["switch", normalized_branch_name]
    _run_git_command(repo_root, command)
    current_branch = _run_git_command(repo_root, ["branch", "--show-current"]).stdout.strip()
    return {
        "ok": True,
        "repo_path": str(repo_root),
        "current_branch": current_branch or None,
    }


@git_server.tool(
    description="Push one local branch to a remote and set upstream tracking.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False),
)
def push_git_branch(
    branch_name: str,
    repo_path: str = ".",
    cwd: str | None = None,
    remote: str = "origin",
) -> dict[str, Any]:
    """Push one branch to the requested remote."""
    repo_root = _resolve_git_repo_root(repo_path, cwd=cwd)
    normalized_branch_name = _normalize_required_string(branch_name, field_name="branch_name")
    normalized_remote = _normalize_required_string(remote, field_name="remote")
    _run_git_command(repo_root, ["push", "-u", normalized_remote, normalized_branch_name])
    return {
        "ok": True,
        "repo_path": str(repo_root),
        "branch_name": normalized_branch_name,
        "remote": normalized_remote,
    }


@git_server.tool(
    description="List changed tracked and untracked paths in one repository.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def list_git_changed_paths(repo_path: str = ".", cwd: str | None = None) -> dict[str, Any]:
    """Return the current changed path set for one repository."""
    repo_root = _resolve_git_repo_root(repo_path, cwd=cwd)
    porcelain = _run_git_command(repo_root, ["status", "--short"]).stdout.splitlines()
    paths = []
    for line in porcelain:
        if len(line) < 4:
            continue
        paths.append(line[3:].strip())
    return {
        "ok": True,
        "repo_path": str(repo_root),
        "paths": paths,
    }


def _git_env() -> dict[str, str]:
    """Return a copy of the current environment with git interactive prompts disabled."""
    env = os.environ.copy()
    # Prevent git from opening an interactive prompt (credential helper, confirm, etc.)
    # which would deadlock the MCP stdio channel.
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _run_git_command(repo_root: Path, args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    """Run one git command in a repository root."""
    completed_process = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        env=_git_env(),
        timeout=timeout,
    )
    if completed_process.returncode != 0:
        stderr = completed_process.stderr.strip() or completed_process.stdout.strip()
        raise ValueError(stderr or f"Git command failed: git {' '.join(args)}")
    return completed_process


def _resolve_git_repo_root(repo_path: str, *, cwd: str | None) -> Path:
    """Resolve one repository path and return its top-level root."""
    root = Path.cwd().resolve() if cwd is None else Path(cwd).expanduser().resolve(strict=False)
    candidate_path = Path(repo_path).expanduser()
    if not candidate_path.is_absolute():
        candidate_path = root / candidate_path
    resolved_path = candidate_path.resolve(strict=False)
    if not resolved_path.exists():
        raise ValueError(f"Path '{resolved_path}' does not exist.")
    target_dir = resolved_path if resolved_path.is_dir() else resolved_path.parent
    completed_process = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=target_dir,
        text=True,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        env=_git_env(),
        timeout=10,
    )
    if completed_process.returncode != 0:
        raise ValueError(f"Path '{resolved_path}' is not inside a git repository.")
    return Path(completed_process.stdout.strip()).resolve(strict=False)


def _normalize_required_string(value: str, *, field_name: str) -> str:
    """Return one validated non-empty string."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Tool field '{field_name}' must be a non-empty string.")
    return value.strip()


def _normalize_pathspecs(
    pathspecs: list[str] | None,
    *,
    field_name: str = "pathspecs",
) -> tuple[str, ...]:
    """Return normalized pathspecs."""
    if pathspecs is None:
        return ()
    if not isinstance(pathspecs, list):
        raise ValueError(f"Tool field '{field_name}' must be a list when provided.")
    normalized_values: list[str] = []
    seen_values: set[str] = set()
    for index, raw_item in enumerate(pathspecs):
        if not isinstance(raw_item, str) or not raw_item.strip():
            raise ValueError(f"Tool field '{field_name}[{index}]' must be a non-empty string.")
        normalized_item = raw_item.strip()
        if normalized_item in seen_values:
            continue
        seen_values.add(normalized_item)
        normalized_values.append(normalized_item)
    return tuple(normalized_values)


def _parse_status_entry(line: str) -> dict[str, Any]:
    """Parse one porcelain status line."""
    if len(line) < 3:
        return {"index_status": None, "worktree_status": None, "path": line.strip()}
    return {
        "index_status": line[0],
        "worktree_status": line[1],
        "path": line[3:].strip(),
    }


def main() -> None:
    """Run the git MCP server over stdio."""
    build_git_server().run(transport="stdio")


if __name__ == "__main__":
    main()
