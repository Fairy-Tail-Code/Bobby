from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from infrastructure.paths import get_default_runtime_cwd


docker_server = FastMCP("openharness-docker", log_level="ERROR")


def build_docker_server() -> FastMCP:
    """Return the configured docker MCP server instance."""
    return docker_server


@docker_server.tool(
    description="List Docker containers with normalized metadata.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def list_docker_containers(all_containers: bool = True) -> dict[str, Any]:
    """List containers from the local Docker daemon."""
    command = [
        "docker",
        "ps",
        "--format",
        "{{json .}}",
    ]
    if all_containers:
        command.insert(2, "-a")
    completed_process = _run_command(command)
    containers = []
    for line in completed_process.stdout.splitlines():
        if not line.strip():
            continue
        raw_item = json.loads(line)
        containers.append(
            {
                "id": raw_item.get("ID"),
                "image": raw_item.get("Image"),
                "command": raw_item.get("Command"),
                "created_at": raw_item.get("RunningFor"),
                "status": raw_item.get("Status"),
                "ports": raw_item.get("Ports"),
                "names": raw_item.get("Names"),
            }
        )
    return {
        "ok": True,
        "containers": containers,
    }


@docker_server.tool(
    description="List local Docker images.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def list_docker_images() -> dict[str, Any]:
    """List images from the local Docker daemon."""
    completed_process = _run_command(
        [
            "docker",
            "images",
            "--format",
            "{{json .}}",
        ]
    )
    images = []
    for line in completed_process.stdout.splitlines():
        if not line.strip():
            continue
        raw_item = json.loads(line)
        images.append(
            {
                "repository": raw_item.get("Repository"),
                "tag": raw_item.get("Tag"),
                "id": raw_item.get("ID"),
                "created_since": raw_item.get("CreatedSince"),
                "size": raw_item.get("Size"),
            }
        )
    return {
        "ok": True,
        "images": images,
    }


@docker_server.tool(
    description="Inspect one Docker container or service container by id or name.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def inspect_docker_container(container: str) -> dict[str, Any]:
    """Return normalized container inspection details."""
    normalized_container = _normalize_required_string(container, field_name="container")
    completed_process = _run_command(["docker", "inspect", normalized_container])
    payload = json.loads(completed_process.stdout)
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"No inspection data returned for container '{normalized_container}'.")
    raw_item = payload[0]
    state = raw_item.get("State") if isinstance(raw_item, dict) else {}
    config = raw_item.get("Config") if isinstance(raw_item, dict) else {}
    host_config = raw_item.get("HostConfig") if isinstance(raw_item, dict) else {}
    network_settings = raw_item.get("NetworkSettings") if isinstance(raw_item, dict) else {}
    return {
        "ok": True,
        "id": raw_item.get("Id"),
        "name": raw_item.get("Name"),
        "image": config.get("Image") if isinstance(config, dict) else None,
        "command": config.get("Cmd") if isinstance(config, dict) else None,
        "status": state.get("Status") if isinstance(state, dict) else None,
        "running": state.get("Running") if isinstance(state, dict) else None,
        "exit_code": state.get("ExitCode") if isinstance(state, dict) else None,
        "started_at": state.get("StartedAt") if isinstance(state, dict) else None,
        "finished_at": state.get("FinishedAt") if isinstance(state, dict) else None,
        "restart_policy": host_config.get("RestartPolicy") if isinstance(host_config, dict) else None,
        "ports": network_settings.get("Ports") if isinstance(network_settings, dict) else None,
    }


@docker_server.tool(
    description="View logs from one Docker container.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def view_docker_logs(
    container: str,
    tail: int = 200,
    timestamps: bool = False,
) -> dict[str, Any]:
    """Return recent logs from one container."""
    normalized_container = _normalize_required_string(container, field_name="container")
    _validate_positive_int(tail, field_name="tail")
    command = ["docker", "logs", "--tail", str(tail)]
    if timestamps:
        command.append("--timestamps")
    command.append(normalized_container)
    completed_process = _run_command(command)
    return {
        "ok": True,
        "container": normalized_container,
        "logs": completed_process.stdout if completed_process.stdout else completed_process.stderr,
    }


@docker_server.tool(
    description="List services declared for one Docker Compose project.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def list_compose_services(
    project_path: str = ".",
    cwd: str | None = None,
    compose_files: list[str] | None = None,
) -> dict[str, Any]:
    """List compose services."""
    project_root = _resolve_project_path(project_path, cwd=cwd)
    completed_process = _run_compose_command(
        project_root=project_root,
        compose_files=compose_files,
        args=["config", "--services"],
    )
    services = [line.strip() for line in completed_process.stdout.splitlines() if line.strip()]
    return {
        "ok": True,
        "project_path": str(project_root),
        "services": services,
    }


@docker_server.tool(
    description="Inspect runtime status for one Docker Compose project.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def inspect_compose_status(
    project_path: str = ".",
    cwd: str | None = None,
    compose_files: list[str] | None = None,
) -> dict[str, Any]:
    """Return normalized status for compose services."""
    project_root = _resolve_project_path(project_path, cwd=cwd)
    completed_process = _run_compose_command(
        project_root=project_root,
        compose_files=compose_files,
        args=["ps", "--format", "json"],
    )
    payload = json.loads(completed_process.stdout or "[]")
    services = []
    if isinstance(payload, list):
        for raw_item in payload:
            if not isinstance(raw_item, dict):
                continue
            services.append(
                {
                    "name": raw_item.get("Name"),
                    "service": raw_item.get("Service"),
                    "state": raw_item.get("State"),
                    "status": raw_item.get("Status"),
                    "health": raw_item.get("Health"),
                    "publishers": raw_item.get("Publishers"),
                }
            )
    return {
        "ok": True,
        "project_path": str(project_root),
        "services": services,
    }


@docker_server.tool(
    description="Start one or more Docker Compose services.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False),
)
def start_compose_services(
    project_path: str = ".",
    cwd: str | None = None,
    compose_files: list[str] | None = None,
    services: list[str] | None = None,
    build: bool = False,
    detach: bool = True,
) -> dict[str, Any]:
    """Start one or more compose services."""
    project_root = _resolve_project_path(project_path, cwd=cwd)
    normalized_services = _normalize_optional_string_list(services, field_name="services")
    command = ["up"]
    if detach:
        command.append("-d")
    if build:
        command.append("--build")
    command.extend(normalized_services)
    completed_process = _run_compose_command(
        project_root=project_root,
        compose_files=compose_files,
        args=command,
    )
    return {
        "ok": True,
        "project_path": str(project_root),
        "services": list(normalized_services),
        "output": completed_process.stdout or completed_process.stderr,
    }


@docker_server.tool(
    description="Stop or remove one Docker Compose project or selected services.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False),
)
def stop_compose_services(
    project_path: str = ".",
    cwd: str | None = None,
    compose_files: list[str] | None = None,
    services: list[str] | None = None,
    remove: bool = False,
    remove_volumes: bool = False,
) -> dict[str, Any]:
    """Stop or tear down compose services."""
    project_root = _resolve_project_path(project_path, cwd=cwd)
    normalized_services = _normalize_optional_string_list(services, field_name="services")
    if remove and normalized_services:
        raise ValueError("Tool 'stop_compose_services' cannot combine 'remove=true' with explicit services.")
    command = ["down"] if remove else ["stop"]
    if remove and remove_volumes:
        command.append("-v")
    command.extend(normalized_services)
    completed_process = _run_compose_command(
        project_root=project_root,
        compose_files=compose_files,
        args=command,
    )
    return {
        "ok": True,
        "project_path": str(project_root),
        "services": list(normalized_services),
        "removed": remove,
        "output": completed_process.stdout or completed_process.stderr,
    }


@docker_server.tool(
    description="Run one command inside a Docker Compose service container.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False),
)
def run_compose_service_command(
    service: str,
    command: list[str],
    project_path: str = ".",
    cwd: str | None = None,
    compose_files: list[str] | None = None,
    no_deps: bool = False,
) -> dict[str, Any]:
    """Run one command inside a compose service."""
    project_root = _resolve_project_path(project_path, cwd=cwd)
    normalized_service = _normalize_required_string(service, field_name="service")
    normalized_command = _normalize_required_string_list(command, field_name="command")
    args = ["run", "--rm"]
    if no_deps:
        args.append("--no-deps")
    args.append(normalized_service)
    args.extend(normalized_command)
    completed_process = _run_compose_command(
        project_root=project_root,
        compose_files=compose_files,
        args=args,
    )
    return {
        "ok": True,
        "project_path": str(project_root),
        "service": normalized_service,
        "command": list(normalized_command),
        "stdout": completed_process.stdout,
        "stderr": completed_process.stderr,
    }


def _run_compose_command(
    *,
    project_root: Path,
    compose_files: list[str] | None,
    args: list[str],
) -> subprocess.CompletedProcess[str]:
    """Run one docker compose command from a project root."""
    command = ["docker", "compose"]
    for compose_file in _normalize_optional_string_list(compose_files, field_name="compose_files"):
        command.extend(["-f", compose_file])
    command.extend(args)
    return _run_command(command, cwd=project_root)


def _run_command(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run one subprocess command and raise a normalized error on failure."""
    completed_process = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        stdin=subprocess.DEVNULL,
    )
    if completed_process.returncode != 0:
        error_text = completed_process.stderr.strip() or completed_process.stdout.strip()
        raise ValueError(error_text or f"Command failed: {' '.join(command)}")
    return completed_process


def _resolve_project_path(project_path: str, *, cwd: str | None) -> Path:
    """Resolve one compose project root."""
    normalized_project_path = _normalize_required_string(project_path, field_name="project_path")
    base_dir = get_default_runtime_cwd() if cwd is None else Path(cwd).expanduser().resolve(strict=False)
    candidate_path = Path(normalized_project_path).expanduser()
    if not candidate_path.is_absolute():
        candidate_path = base_dir / candidate_path
    resolved_path = candidate_path.resolve(strict=False)
    if not resolved_path.exists():
        raise ValueError(f"Project path '{resolved_path}' does not exist.")
    if not resolved_path.is_dir():
        raise ValueError(f"Project path '{resolved_path}' is not a directory.")
    return resolved_path


def _normalize_required_string(value: str, *, field_name: str) -> str:
    """Return one validated non-empty string."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Tool field '{field_name}' must be a non-empty string.")
    return value.strip()


def _normalize_required_string_list(value: list[str], *, field_name: str) -> tuple[str, ...]:
    """Return one validated non-empty string list."""
    normalized_values = _normalize_optional_string_list(value, field_name=field_name)
    if not normalized_values:
        raise ValueError(f"Tool field '{field_name}' must contain at least one string.")
    return normalized_values


def _normalize_optional_string_list(value: list[str] | None, *, field_name: str) -> tuple[str, ...]:
    """Return one normalized optional string list."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"Tool field '{field_name}' must be a list when provided.")
    normalized_values: list[str] = []
    seen_values: set[str] = set()
    for index, raw_item in enumerate(value):
        if not isinstance(raw_item, str) or not raw_item.strip():
            raise ValueError(f"Tool field '{field_name}[{index}]' must be a non-empty string.")
        normalized_item = raw_item.strip()
        if normalized_item in seen_values:
            continue
        seen_values.add(normalized_item)
        normalized_values.append(normalized_item)
    return tuple(normalized_values)


def _validate_positive_int(value: int, *, field_name: str) -> None:
    """Validate one positive integer field."""
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"Tool field '{field_name}' must be a positive integer.")


def main() -> None:
    """Run the docker MCP server over stdio."""
    build_docker_server().run(transport="stdio")


if __name__ == "__main__":
    main()
