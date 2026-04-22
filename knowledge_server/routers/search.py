from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from knowledge_server.models import SearchRequest, SearchResponse
from knowledge_server.routers.auth import get_current_user
from knowledge_server.services.search_service import search_experiences

router = APIRouter()


@router.post("", response_model=SearchResponse)
async def search(
    request: Request,
    body: SearchRequest,
    user=Depends(get_current_user),
):
    return await search_experiences(request.app.state.db, body)


@router.get("", response_model=SearchResponse)
async def search_get(
    request: Request,
    q: str,
    limit: int = 20,
    offset: int = 0,
    user=Depends(get_current_user),
):
    body = SearchRequest(query=q, limit=limit, offset=offset)
    return await search_experiences(request.app.state.db, body)
