from fastapi import APIRouter

from app.api.routes import (
    candidates,
    demo_replay,
    documents,
    events,
    lens_run,
    lens_sessions,
    login,
    private,
    sessions,
    users,
    utils,
)
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(documents.router)
api_router.include_router(sessions.router)
api_router.include_router(candidates.router)
api_router.include_router(events.router)
api_router.include_router(demo_replay.router)
api_router.include_router(lens_run.router)
api_router.include_router(lens_sessions.router)


if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
