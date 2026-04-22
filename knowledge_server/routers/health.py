from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok"}


@router.get("/stats")
async def get_stats(request: Request):
    db = request.app.state.db
    cursor = await db.conn.execute("SELECT COUNT(*) as count FROM experiences")
    row = await cursor.fetchone()
    return {"total_experiences": row["count"]}
