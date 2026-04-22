from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from knowledge_server.config import ServerConfig
from knowledge_server.database import Database
from knowledge_server.routers import auth, experiences, health, search, sync


def create_app(config: ServerConfig | None = None) -> FastAPI:
    config = config or ServerConfig.from_env()
    db = Database(config.db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await db.connect()
        app.state.db = db
        app.state.config = config
        yield
        await db.close()

    app = FastAPI(
        title="OpenHarness Knowledge Server",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(experiences.router, prefix="/api/v1/experiences", tags=["experiences"])
    app.include_router(sync.router, prefix="/api/v1/sync", tags=["sync"])
    app.include_router(search.router, prefix="/api/v1/search", tags=["search"])

    return app
