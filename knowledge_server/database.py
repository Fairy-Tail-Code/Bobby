from __future__ import annotations

from pathlib import Path

import aiosqlite

_DEFAULT_DB = Path(__file__).parent.parent / "knowledge_server.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    client_id TEXT UNIQUE NOT NULL,
    display_name TEXT DEFAULT '',
    api_key_hash TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    last_sync_at TEXT
);

CREATE TABLE IF NOT EXISTS experiences (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    tags TEXT DEFAULT '[]',
    content TEXT NOT NULL,
    context TEXT DEFAULT '{}',
    source_session_id TEXT,
    source_agent TEXT,
    project_type TEXT,
    visibility TEXT DEFAULT 'private',
    source_client_id TEXT NOT NULL,
    client_timestamp TEXT,
    content_hash TEXT UNIQUE,
    version INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_experiences_category ON experiences(category);
CREATE INDEX IF NOT EXISTS idx_experiences_client ON experiences(source_client_id);
CREATE INDEX IF NOT EXISTS idx_experiences_created ON experiences(created_at);

CREATE VIRTUAL TABLE IF NOT EXISTS experiences_fts USING fts5(
    title, content, tags, category,
    content=experiences, content_rowid=id
);

CREATE TRIGGER IF NOT EXISTS experiences_ai AFTER INSERT ON experiences BEGIN
    INSERT INTO experiences_fts(rowid, title, content, tags, category)
    VALUES (new.rowid, new.title, new.content, new.tags, new.category);
END;

CREATE TRIGGER IF NOT EXISTS experiences_ad AFTER DELETE ON experiences BEGIN
    INSERT INTO experiences_fts(experiences_fts, rowid, title, content, tags, category)
    VALUES ('delete', old.rowid, old.title, old.content, old.tags, old.category);
END;

CREATE TRIGGER IF NOT EXISTS experiences_au AFTER UPDATE ON experiences BEGIN
    INSERT INTO experiences_fts(experiences_fts, rowid, title, content, tags, category)
    VALUES ('delete', old.rowid, old.title, old.content, old.tags, old.category);
    INSERT INTO experiences_fts(rowid, title, content, tags, category)
    VALUES (new.rowid, new.title, new.content, new.tags, new.category);
END;

CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    count INTEGER DEFAULT 0,
    timestamp TEXT DEFAULT (datetime('now'))
);
"""


class Database:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = str(db_path or _DEFAULT_DB)
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn
