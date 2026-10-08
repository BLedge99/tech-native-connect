"""FastAPI app factory. Routers mounted, error handlers registered."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.db import Base, dispose_engine, engine
from app.errors import (
    AppError,
    app_error_handler,
    http_error_handler,
    validation_error_handler,
)
from app.routers import admin, auth, connections, ideas, matches, messaging, notifications, users

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    log.info("Bootcamp Connect starting — env=%s", settings.app_env)
    if not settings.seed_admin_password:
        log.warning(
            "SEED_ADMIN_PASSWORD is not set. Run `python -m app.seed` after "
            "setting it, or the admin logins will not be created."
        )
    yield
    await dispose_engine()


settings = get_settings()

app = FastAPI(
    title="Bootcamp Connect",
    version="0.1.0",
    description=(
        "Connects software developers with business developers on the same "
        "bootcamp course. See AGENTS.md and specs/ for the full specification."
    ),
    lifespan=lifespan,
)

# Same-origin in dev via the Vite proxy; CORS is for direct API use.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,   # required for the session cookie
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(StarletteHTTPException, http_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(matches.router)
app.include_router(connections.router)
app.include_router(messaging.router)
app.include_router(messaging.ws_router)
app.include_router(notifications.router)
app.include_router(ideas.router)
app.include_router(admin.router)

# Dev-only routes (video serving for the dev panel)
if settings.app_env == "development":
    from app.dev import router as dev_router
    app.include_router(dev_router)


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    """Log the traceback server-side, return a generic message. Never leak
    internals to the client — and never let one failure blank a demo page."""
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    from app.errors import error_body
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=500,
        content=error_body("internal_error", "Something went wrong on our end."),
    )


@app.get("/api/v1/health")
async def health():
    """Liveness plus a DB check — a green health endpoint that cannot reach
    Postgres is worse than a red one."""
    from sqlalchemy import text

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception as exc:  # noqa: BLE001
        log.error("Health check failed: %s", exc)
        return {"status": "degraded", "database": "unreachable"}