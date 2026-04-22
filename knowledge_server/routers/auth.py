from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from knowledge_server.services.auth_service import generate_id, hash_api_key

router = APIRouter()


class RegisterRequest:
    def __init__(self, client_id: str = "", display_name: str = "", api_key: str = ""):
        self.client_id = client_id or generate_id()
        self.display_name = display_name
        self.api_key = api_key


async def get_current_user(request: Request):
    """Dependency that validates the API key from the X-API-Key header."""
    api_key = request.headers.get("X-API-Key", "")
    config = request.app.state.config
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    # Master key check
    if config.master_api_key and api_key == config.master_api_key:
        return {"client_id": "master"}

    # User lookup
    db = request.app.state.db
    cursor = await db.conn.execute(
        "SELECT client_id, api_key_hash FROM users WHERE api_key_hash = ?",
        (hash_api_key(api_key),),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return {"client_id": row["client_id"]}


@router.post("/register")
async def register(request: Request):
    """Register a new CLI client. Returns the client_id and api_key."""
    body = await request.json()
    client_id = body.get("client_id") or generate_id()
    display_name = body.get("display_name", "")
    api_key = body.get("api_key") or generate_id()
    api_key_hash = hash_api_key(api_key)

    db = request.app.state.db
    try:
        await db.conn.execute(
            "INSERT INTO users (id, client_id, display_name, api_key_hash) VALUES (?, ?, ?, ?)",
            (generate_id(), client_id, display_name, api_key_hash),
        )
        await db.conn.commit()
    except Exception:
        raise HTTPException(status_code=409, detail="Client ID already registered")

    return {"client_id": client_id, "api_key": api_key}


@router.post("/token")
async def create_token(request: Request, user=Depends(get_current_user)):
    """Validate API key and return confirmation."""
    return {"client_id": user["client_id"], "status": "ok"}
