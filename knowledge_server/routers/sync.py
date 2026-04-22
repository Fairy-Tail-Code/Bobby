from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from knowledge_server.models import SyncPullRequest, SyncPullResponse, SyncPushRequest, SyncPushResponse
from knowledge_server.routers.auth import get_current_user
from knowledge_server.services import experience_service

router = APIRouter()


@router.post("/push", response_model=SyncPushResponse)
async def sync_push(
    request: Request,
    body: SyncPushRequest,
    user=Depends(get_current_user),
):
    return await experience_service.sync_push(request.app.state.db, body)


@router.post("/pull", response_model=SyncPullResponse)
async def sync_pull(
    request: Request,
    body: SyncPullRequest,
    user=Depends(get_current_user),
):
    return await experience_service.sync_pull(request.app.state.db, body)
