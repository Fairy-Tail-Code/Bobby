from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from openharness.repositories import GiteeBackend


gitee_server = FastMCP("openharness-gitee", log_level="ERROR")


def build_gitee_server() -> FastMCP:
    """Return the configured Gitee MCP server instance."""
    return gitee_server


@gitee_server.tool(
    description="Return the authenticated Gitee user profile.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True),
)
def get_gitee_current_user() -> dict[str, Any]:
    """Return the current authenticated Gitee user."""
    payload = GiteeBackend().get_current_user()
    return {
        "ok": True,
        "user": payload,
    }


@gitee_server.tool(
    description="Return one Gitee repository when it exists.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True),
)
def get_gitee_repository(owner: str, repo_name: str) -> dict[str, Any]:
    """Return one Gitee repository payload or a not-found result."""
    backend = GiteeBackend()
    payload = backend.get_repository(owner.strip(), repo_name.strip())
    if payload is None:
        return {
            "ok": True,
            "found": False,
            "owner": owner.strip(),
            "repo_name": repo_name.strip(),
        }
    return {
        "ok": True,
        "found": True,
        "repository": payload,
        "clone_url": backend.resolve_clone_url(payload),
    }


@gitee_server.tool(
    description="Create one Gitee repository under the authenticated account or organization.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
)
def create_gitee_repository(
    repo_name: str,
    owner: str | None = None,
    private: bool = False,
    description: str | None = None,
) -> dict[str, Any]:
    """Create one Gitee repository and return its metadata."""
    backend = GiteeBackend()
    payload = backend.create_repository(
        name=repo_name.strip(),
        owner=owner.strip() if isinstance(owner, str) and owner.strip() else None,
        private=private,
        description=description.strip() if isinstance(description, str) and description.strip() else None,
    )
    return {
        "ok": True,
        "repository": payload,
        "clone_url": backend.resolve_clone_url(payload),
    }


def main() -> None:
    """Run the Gitee MCP server over stdio."""
    build_gitee_server().run(transport="stdio")


if __name__ == "__main__":
    main()
