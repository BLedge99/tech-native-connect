from contextlib import asynccontextmanager

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.db import engine
from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.matches import router as matches_router
from app.routers.messaging import router as messaging_router
from app.routers.connections import router as connections_router
from app.routers.notifications import router as notifications_router
from app.routers.profiles import router as profiles_router
from app.routers.ideas import router as ideas_router
from app.web import ApiError


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title="Bootcamp Connect API", version="1.0.0", lifespan=lifespan)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
app.include_router(auth_router)
app.include_router(profiles_router)
app.include_router(matches_router)
app.include_router(connections_router)
app.include_router(messaging_router)
app.include_router(notifications_router)
app.include_router(ideas_router)
app.include_router(admin_router)


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    error = {"code": exc.code, "message": exc.message}
    if exc.fields is not None:
        error["fields"] = exc.fields
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": error},
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code, message = {
        401: ("unauthenticated", "Sign in to continue."),
        403: ("forbidden", "You do not have permission to do that."),
        404: ("not_found", "Not found."),
        405: ("bad_request", "This request is not supported."),
    }.get(exc.status_code, ("bad_request", "The request could not be completed."))
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": code, "message": message}})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    fields = {".".join(map(str, error["loc"][1:])): error["msg"] for error in errors}
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Some fields need attention.",
                "fields": fields,
            }
        },
    )


@app.exception_handler(Exception)
async def internal_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logging.getLogger(__name__).exception("Unhandled API error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": "An unexpected error occurred."}},
    )


@app.get("/api/v1/health")
async def health() -> dict[str, str]:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ok"}