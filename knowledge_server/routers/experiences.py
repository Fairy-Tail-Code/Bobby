from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from knowledge_server.models import ExperienceCategory, ExperienceCreate, ExperienceResponse
from knowledge_server.routers.auth import get_current_user
from knowledge_server.services import experience_service

router = APIRouter()


@router.post("", response_model=ExperienceResponse)
async def create_experience(
    request: Request,
    exp: ExperienceCreate,
    user=Depends(get_current_user),
):
    result = await experience_service.create_experience(request.app.state.db, exp)
    if result is None:
        raise HTTPException(status_code=409, detail="Duplicate experience")
    return result


@router.get("/{exp_id}", response_model=ExperienceResponse | None)
async def get_experience(request: Request, exp_id: str):
    result = await experience_service.get_experience(request.app.state.db, exp_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Experience not found")
    return result


@router.get("", response_model=list[ExperienceResponse])
async def list_experiences(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    category: str | None = None,
):
    return await experience_service.list_experiences(
        request.app.state.db, limit=limit, offset=offset, category=category,
    )


@router.delete("/{exp_id}")
async def delete_experience(
    request: Request,
    exp_id: str,
    user=Depends(get_current_user),
):
    deleted = await experience_service.delete_experience(request.app.state.db, exp_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Experience not found")
    return {"status": "deleted"}
