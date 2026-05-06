from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_queue (
    id TEXT PRIMARY KEY,
    experience_json TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT (datetime('now')),
    synced_at TEXT,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_kq_status ON knowledge_queue(status);
"""


class LocalKnowledgeStore:
    """Local SQLite queue for experiences pending sync."""

    def __init__(self, store_path: str | Path | None = None):
        if store_path is None:
            from utils.paths import get_home
            store_path = get_home() / "knowledge_queue.db"
        self._path = Path(store_path)
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self._path))
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def __aenter__(self) -> LocalKnowledgeStore:
        await self.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Store not connected. Call connect() first.")
        return self._conn

    async def enqueue(self, experiences: list[dict]) -> int:
        """Add experiences to the pending queue."""
        count = 0
        for exp in experiences:
            exp_id = exp.get("title", "")[:50] + "_" + datetime.now().strftime("%Y%m%d%H%M%S%f")
            await self.conn.execute(
                "INSERT OR IGNORE INTO knowledge_queue (id, experience_json) VALUES (?, ?)",
                (exp_id, json.dumps(exp, ensure_ascii=False)),
            )
            count += 1
        await self.conn.commit()
        return count

    async def get_pending(self, limit: int = 50) -> list[tuple[str, dict]]:
        """Get pending experiences ready for sync."""
        cursor = await self.conn.execute(
            "SELECT id, experience_json FROM knowledge_queue WHERE status = 'pending' LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [(row["id"], json.loads(row["experience_json"])) for row in rows]

    async def mark_synced(self, ids: list[str]) -> None:
        """Mark experiences as successfully synced."""
        for exp_id in ids:
            await self.conn.execute(
                "UPDATE knowledge_queue SET status = 'synced', synced_at = ? WHERE id = ?",
                (datetime.now().isoformat(), exp_id),
            )
        await self.conn.commit()

    async def mark_failed(self, exp_id: str, error: str) -> None:
        """Mark an experience as failed with error info."""
        await self.conn.execute(
            "UPDATE knowledge_queue SET status = 'failed', error_message = ?, retry_count = retry_count + 1 WHERE id = ?",
            (error[:500], exp_id),
        )
        await self.conn.commit()

    async def get_status(self) -> dict:
        """Get queue status summary."""
        cursor = await self.conn.execute(
            "SELECT status, COUNT(*) as count FROM knowledge_queue GROUP BY status"
        )
        rows = await cursor.fetchall()
        return {row["status"]: row["count"] for row in rows}

    async def cleanup_old(self, days: int = 30) -> int:
        """Remove synced entries older than N days."""
        cursor = await self.conn.execute(
            "DELETE FROM knowledge_queue WHERE status = 'synced' AND synced_at < datetime('now', ?)",
            (f"-{days} days",),
        )
        await self.conn.commit()
        return cursor.rowcount
