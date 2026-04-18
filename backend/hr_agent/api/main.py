from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hr_agent.config import get_settings
from hr_agent.db.session import init_db
from hr_agent.api.routes import candidates, dashboard, health, roles
from hr_agent.api.ws import chatbot as ws_chat
from hr_agent.api.ws import interview as ws_interview


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix="/api")
    app.include_router(roles.router, prefix="/api")
    app.include_router(candidates.router, prefix="/api")
    app.include_router(dashboard.router, prefix="/api")
    app.include_router(ws_interview.router)
    app.include_router(ws_chat.router)
    return app


app = create_app()
