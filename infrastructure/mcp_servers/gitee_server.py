from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations


gitee_server = FastMCP("openharness-gitee", log_level="ERROR")

_GITEE_BASE_URL = os.environ.get("GITEE_BASE_URL", "https://gitee.com/api/v5")


class _GiteeBackend:
    """Minimal Gitee API client using access token from environment."""

    def __init__(self) -> None:
        self._token = os.environ.get("GITEE_ACCESS_TOKEN", "")
        self._base_url = _GITEE_BASE_URL

    def get_current_user(self) -> dict[str, Any]:
        with httpx.Client(timeout=15) as client:
            response = client.get(f"{self._base_url}/user", params={"access_token": self._token})
            response.raise_for_status()
            return response.json()

    def get_repository(self, owner: str, repo_name: str) -> dict[str, Any] | None:
        with httpx.Client(timeout=15) as client:
            response = client.get(
                f"{self._base_url}/repos/{owner}/{repo_name}",
                params={"access_token": self._token},
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()

    def create_repository(
        self,
        name: str,
        owner: str | None = None,
        private: bool = False,
        description: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "access_token": self._token,
            "name": name,
            "private": private,
        }
        if description:
            payload["description"] = description
        url = f"{self._base_url}/user/repos"
        if owner:
            url = f"{self._base_url}/orgs/{owner}/repos"
        with httpx.Client(timeout=15) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            return response.json()

    def resolve_clone_url(self, payload: dict[str, Any]) -> str | None:
        ssh_url = payload.get("ssh_url")
        if isinstance(ssh_url, str) and ssh_url:
            return ssh_url
        html_url = payload.get("html_url")
        if isinstance(html_url, str) and html_url:
            return f"{html_url}.git"
        return None


def build_gitee_server() -> FastMCP:
    """Return the configured Gitee MCP server instance."""
    return gitee_server


@gitee_server.tool(
    description="Return the authenticated Gitee user profile.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True),
)
def get_gitee_current_user() -> dict[str, Any]:
    """Return the current authenticated Gitee user."""
    payload = _GiteeBackend().get_current_user()
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
    backend = _GiteeBackend()
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
    backend = _GiteeBackend()
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
