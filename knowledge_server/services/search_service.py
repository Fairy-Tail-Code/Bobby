from __future__ import annotations

from knowledge_server.models import ExperienceCategory, ExperienceResponse, SearchRequest, SearchResponse
from knowledge_server.services.experience_service import _row_to_response


async def search_experiences(db, request: SearchRequest) -> SearchResponse:
    """Search experiences using FTS5 full-text search."""
    query = request.query
    limit = request.limit
    offset = request.offset

    # Build FTS query
    fts_query = query.replace('"', '""')

    sql = """
        SELECT e.*, rank
        FROM experiences_fts f
        JOIN experiences e ON e.rowid = f.rowid
        WHERE experiences_fts MATCH ?
    """
    params: list = [fts_query]

    if request.categories:
        placeholders = ",".join("?" * len(request.categories))
        sql += f" AND e.category IN ({placeholders})"
        params.extend(c.value for c in request.categories)

    sql += " ORDER BY f.rank LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor = await db.conn.execute(sql, params)
    rows = await cursor.fetchall()

    # Count total
    count_sql = """
        SELECT COUNT(*) as total
        FROM experiences_fts f
        JOIN experiences e ON e.rowid = f.rowid
        WHERE experiences_fts MATCH ?
    """
    count_params: list = [fts_query]
    if request.categories:
        placeholders = ",".join("?" * len(request.categories))
        count_sql += f" AND e.category IN ({placeholders})"
        count_params.extend(c.value for c in request.categories)

    count_cursor = await db.conn.execute(count_sql, count_params)
    total_row = await count_cursor.fetchone()
    total = total_row["total"] if total_row else 0

    return SearchResponse(
        results=[_row_to_response(r) for r in rows],
        total=total,
        query=query,
    )
