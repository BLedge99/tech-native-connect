"""FastAPI app factory. Routers mounted, error handlers registered.

When `static/` exists — the Docker build puts the built SPA there — this app
also serves the frontend, so the browser, the API and the WebSocket are one
origin. That is the point: no CORS, no cookie domain, no proxy. In dev the
Vite dev server does the same job, and `static/` does not exist.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.db import Base, dispose_engine, engine
from app.errors import AppError, NotFound, app_error_handler, http_error_handler, validation_error_handler
from app.routers import admin, auth, connections, ideas, matches, messaging, notifications, users
from app.security import SecurityMiddleware

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# Same policy the Vite dev server serves (frontend/vite.config.ts). Applied
# here because in production there is no Vite server to do it.
#
# style-src needs 'unsafe-inline': components/ui.tsx sets style attributes on
# the avatar, which CSP treats as an inline style and blocks without it. Scripts
# stay strict — the built index.html has no inline script.
STATIC_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
    "content-security-policy": (
        "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
        "form-action 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' ws: wss:"
    ),
}


def resolve_static_file(path: str, root: Path) -> Path | None:
    """Map a request path to a file inside `root`, or index.html for a client-side
    route. None if it escapes `root` or the build has no index.html.

    A path from the URL is attacker-controlled, so the containment check is the
    point of this function, not the file lookup.
    """
    root = root.resolve()
    candidate = (root / path).resolve()
    if not candidate.is_relative_to(root):
        return None
    if path and candidate.is_file():
        return candidate
    index = root / "index.html"
    return index if index.is_file() else None



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
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
    openapi_url="/openapi.json" if settings.app_env != "production" else None,
    lifespan=lifespan,
)

# Same-origin in dev via the Vite proxy; CORS is for direct API use.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=r"^https://.*\.trycloudflare\.com$",
    allow_credentials=True,   # required for the session cookie
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
app.add_middleware(SecurityMiddleware, settings=settings)

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


# ─── Frontend ─────────────────────────────────────────────────────────────────
# Registered last so every router above wins. WebSocket routes are matched on
# the websocket scope and are unaffected by this.

if STATIC_DIR.is_dir():
    log.info("Serving the built frontend from %s", STATIC_DIR)

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def serve_spa(full_path: str):
        # An unknown /api path must stay a JSON 404, not the SPA shell.
        if full_path.startswith("api/"):
            raise NotFound("Not found.")
        resolved = resolve_static_file(full_path, STATIC_DIR)
        if resolved is None:
            raise NotFound("Not found.")
        # Vite fingerprints everything under /assets, so it can be cached
        # forever. index.html must not be, or a deploy never reaches a client
        # that already has it.
        cache = (
            "public, max-age=31536000, immutable"
            if resolved.parent.name == "assets"
            else "no-store"
        )
        return FileResponse(
            resolved, headers={**STATIC_HEADERS, "cache-control": cache}
        )
