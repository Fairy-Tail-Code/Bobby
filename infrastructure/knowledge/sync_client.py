from __future__ import annotations

import logging
from datetime import datetime

import httpx

from infrastructure.config import KnowledgeConfig
from infrastructure.knowledge.local_store import LocalKnowledgeStore

logger = logging.getLogger(__name__)


class KnowledgeSyncClient:
    """HTTP client for syncing experiences with the central knowledge server."""

    def __init__(self, config: KnowledgeConfig):
        self._config = config
        self._base_url = config.server_url.rstrip("/")
        self._headers = {"X-API-Key": config.api_key, "Content-Type": "application/json"}

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/v1/health", headers=self._headers)
                return resp.status_code == 200
        except Exception:
            return False

    async def push(self, experiences: list[dict]) -> dict | None:
        """Push experiences to the server."""
        payload = {
            "client_id": self._config.client_id,
            "experiences": experiences,
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/v1/sync/push",
                    json=payload,
                    headers=self._headers,
                )
                if resp.status_code == 200:
                    return resp.json()
                logger.warning("Push failed with status %d: %s", resp.status_code, resp.text)
                return None
        except Exception:
            logger.exception("Push request failed")
            return None

    async def pull(self, since: datetime | None = None) -> dict | None:
        """Pull shared experiences from the server."""
        payload = {
            "client_id": self._config.client_id,
            "since": since.isoformat() if since else None,
            "limit": self._config.batch_size,
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/v1/sync/pull",
                    json=payload,
                    headers=self._headers,
                )
                if resp.status_code == 200:
                    return resp.json()
                logger.warning("Pull failed with status %d: %s", resp.status_code, resp.text)
                return None
        except Exception:
            logger.exception("Pull request failed")
            return None

    async def search(self, query: str, limit: int = 20) -> dict | None:
        """Search experiences on the server."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self._base_url}/api/v1/search",
                    params={"q": query, "limit": limit},
                    headers=self._headers,
                )
                if resp.status_code == 200:
                    return resp.json()
                return None
        except Exception:
            logger.exception("Search request failed")
            return None

    async def sync_with_server(self, local_store: LocalKnowledgeStore) -> dict:
        """Full sync cycle: push pending, then pull new."""
        result = {"pushed": 0, "pulled": 0, "errors": 0}

        # Push pending
        pending = await local_store.get_pending(self._config.batch_size)
        if pending:
            ids, exps = zip(*pending)
            exp_list = list(exps)
            response = await self.push(exp_list)
            if response:
                synced_ids = [ids[i] for i in range(len(ids)) if i < response.get("accepted", 0)]
                await local_store.mark_synced(list(synced_ids))
                result["pushed"] = response.get("accepted", 0)
                # Mark remaining as failed if server reported issues
                for i, exp_id in enumerate(ids):
                    if i >= response.get("accepted", 0):
                        await local_store.mark_failed(exp_id, "Server rejected")
                        result["errors"] += 1
            else:
                for exp_id in ids:
                    await local_store.mark_failed(exp_id, "Server unreachable")
                result["errors"] = len(ids)

        # Pull new
        if self._config.pull_enabled:
            pull_response = await self.pull()
            if pull_response:
                result["pulled"] = len(pull_response.get("experiences", []))

        return result
