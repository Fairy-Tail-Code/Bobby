from __future__ import annotations

import hashlib
import json
from datetime import datetime

from knowledge_server.models import (
    ExperienceCategory,
    ExperienceCreate,
    ExperienceResponse,
    SyncPullRequest,
    SyncPullResponse,
    SyncPushRequest,
    SyncPushResponse,
)
from knowledge_server.services.auth_service import generate_id


def _row_to_response(row) -> ExperienceResponse:
    return ExperienceResponse(
        id=row["id"],
        title=row["title"],
        category=ExperienceCategory(row["category"]),
        tags=json.loads(row["tags"]),
        content=row["content"],
        context=json.loads(row["context"]),
        source_session_id=row["source_session_id"],
        source_agent=row["source_agent"],
        project_type=row["project_type"],
        visibility=row["visibility"],
        source_client_id=row["source_client_id"],
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        content_hash=row["content_hash"] or "",
    )


def _content_hash(exp: ExperienceCreate) -> str:
    return hashlib.sha256(f"{exp.title}|{exp.content}".encode()).hexdigest()


async def create_experience(db, exp: ExperienceCreate) -> ExperienceResponse | None:
    """Insert a single experience. Returns None if duplicate."""
    chash = _content_hash(exp)
    exp_id = generate_id()
    now = datetime.now().isoformat()
    try:
        await db.conn.execute(
            """INSERT INTO experiences
            (id, title, category, tags, content, context, source_session_id,
             source_agent, project_type, visibility, source_client_id,
             client_timestamp, content_hash, version, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (
                exp_id, exp.title, exp.category.value, json.dumps(exp.tags),
                exp.content, json.dumps(exp.context), exp.source_session_id,
                exp.source_agent, exp.project_type, exp.visibility,
                exp.client_id, exp.client_timestamp.isoformat(), chash, now, now,
            ),
        )
        await db.conn.commit()
    except Exception:
        await db.conn.rollback()
        return None

    cursor = await db.conn.execute("SELECT * FROM experiences WHERE id = ?", (exp_id,))
    row = await cursor.fetchone()
    return _row_to_response(row)


async def get_experience(db, exp_id: str) -> ExperienceResponse | None:
    cursor = await db.conn.execute("SELECT * FROM experiences WHERE id = ?", (exp_id,))
    row = await cursor.fetchone()
    return _row_to_response(row) if row else None


async def list_experiences(
    db, *, limit: int = 50, offset: int = 0, category: str | None = None,
) -> list[ExperienceResponse]:
    if category:
        cursor = await db.conn.execute(
            "SELECT * FROM experiences WHERE category = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (category, limit, offset),
        )
    else:
        cursor = await db.conn.execute(
            "SELECT * FROM experiences ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
    rows = await cursor.fetchall()
    return [_row_to_response(r) for r in rows]


async def delete_experience(db, exp_id: str) -> bool:
    cursor = await db.conn.execute("DELETE FROM experiences WHERE id = ?", (exp_id,))
    await db.conn.commit()
    return cursor.rowcount > 0


async def sync_push(db, request: SyncPushRequest) -> SyncPushResponse:
    accepted = 0
    duplicates = 0
    rejected = 0

    for exp in request.experiences:
        result = await create_experience(db, exp)
        if result is not None:
            accepted += 1
        else:
            duplicates += 1

    # Log sync
    sync_id = generate_id()
    await db.conn.execute(
        "INSERT INTO sync_log (client_id, operation, count) VALUES (?, 'push', ?)",
        (request.client_id, accepted),
    )
    await db.conn.commit()

    return SyncPushResponse(
        accepted=accepted,
        duplicates=duplicates,
        rejected=rejected,
        server_sync_id=sync_id,
    )


async def sync_pull(db, request: SyncPullRequest) -> SyncPullResponse:
    query = "SELECT * FROM experiences WHERE 1=1"
    params: list = []

    if request.since:
        query += " AND created_at > ?"
        params.append(request.since.isoformat())

    if request.categories:
        placeholders = ",".join("?" * len(request.categories))
        query += f" AND category IN ({placeholders})"
        params.extend(c.value for c in request.categories)

    # Filter by visibility for the requesting client
    query += " AND (visibility != 'private' OR source_client_id = ?)"
    params.append(request.client_id)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(request.limit + 1)  # Fetch one extra to check has_more

    cursor = await db.conn.execute(query, params)
    rows = await cursor.fetchall()

    has_more = len(rows) > request.limit
    rows = rows[: request.limit]

    # Log sync
    await db.conn.execute(
        "INSERT INTO sync_log (client_id, operation, count) VALUES (?, 'pull', ?)",
        (request.client_id, len(rows)),
    )
    await db.conn.commit()

    return SyncPullResponse(
        experiences=[_row_to_response(r) for r in rows],
        has_more=has_more,
        next_cursor=str(len(rows)) if has_more else None,
    )
