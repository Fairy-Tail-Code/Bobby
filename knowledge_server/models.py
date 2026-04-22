from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ExperienceCategory(str, Enum):
    PROBLEM_SOLUTION = "problem_solution"
    CODE_PATTERN = "code_pattern"
    AGENT_DECISION = "agent_decision"
    ARCHITECTURE = "architecture"
    PITFALL = "pitfall"
    USER_PREFERENCE = "user_preference"
    CONFIG_TRICK = "config_trick"


class ExperienceBase(BaseModel):
    title: str
    category: ExperienceCategory
    tags: list[str] = Field(default_factory=list)
    content: str
    context: dict = Field(default_factory=dict)
    source_session_id: str | None = None
    source_agent: str | None = None
    project_type: str | None = None
    visibility: str = "private"


class ExperienceCreate(ExperienceBase):
    client_id: str
    client_timestamp: datetime = Field(default_factory=datetime.now)


class ExperienceResponse(ExperienceBase):
    id: str
    version: int = 1
    created_at: datetime
    updated_at: datetime
    source_client_id: str
    content_hash: str = ""


class SyncPushRequest(BaseModel):
    client_id: str
    experiences: list[ExperienceCreate]
    last_sync_id: str | None = None


class SyncPushResponse(BaseModel):
    accepted: int
    duplicates: int
    rejected: int
    server_sync_id: str = ""


class SyncPullRequest(BaseModel):
    client_id: str
    since: datetime | None = None
    categories: list[ExperienceCategory] = Field(default_factory=list)
    limit: int = 100


class SyncPullResponse(BaseModel):
    experiences: list[ExperienceResponse]
    has_more: bool = False
    next_cursor: str | None = None


class SearchRequest(BaseModel):
    query: str
    categories: list[ExperienceCategory] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    limit: int = 20
    offset: int = 0


class SearchResponse(BaseModel):
    results: list[ExperienceResponse]
    total: int
    query: str
