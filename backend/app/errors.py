"""Error shape and the exceptions that produce it. Specs/00_conventions.md §2.

Routers raise these; one global handler turns them into the standard body.
No route returns an ad-hoc error dict.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base. Every AppError becomes {"error": {code, message, fields?}}."""

    status_code = 400
    code = "bad_request"

    def __init__(
        self,
        message: str = "",
        *,
        code: str | None = None,
        fields: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message or self.__class__.__doc__ or ""
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.fields = fields
        super().__init__(self.message)


class BadRequest(AppError):
    status_code = 400
    code = "bad_request"
    """The request could not be understood."""


class Unauthenticated(AppError):
    status_code = 401
    code = "unauthenticated"
    """Sign in to continue."""


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"
    """You do not have permission to do that."""


class NotFound(AppError):
    status_code = 404
    code = "not_found"
    """Not found."""


class Conflict(AppError):
    status_code = 409
    code = "already_exists"
    """That conflicts with the current state."""


class PayloadTooLarge(AppError):
    status_code = 413
    code = "file_too_large"
    """That file is too large."""


class UnsupportedMediaType(AppError):
    status_code = 415
    code = "unsupported_media_type"
    """That file type is not supported."""


class ValidationFailed(AppError):
    status_code = 422
    code = "validation_error"
    """Some fields need attention."""

    def __init__(self, fields: dict[str, str], message: str = "Some fields need attention.") -> None:
        super().__init__(message, code="validation_error", fields=fields)


# ─── Named errors used across features ───────────────────────────────────────


class EmailTaken(Conflict):
    """An account with that email already exists."""

    code = "email_taken"


class InvalidCredentials(Unauthenticated):
    """Incorrect email or password."""

    code = "invalid_credentials"


class AccountDeactivated(Forbidden):
    """This account has been deactivated."""

    code = "account_deactivated"


class CsrfFailed(Forbidden):
    """Missing or invalid CSRF token."""

    code = "csrf_failed"


class NotProfileOwner(Forbidden):
    """You can only edit your own profile."""

    code = "not_profile_owner"


class ProfileIncomplete(Forbidden):
    """Choose a role and add at least one skill before browsing matches."""

    code = "profile_incomplete"


class ReceiverProfileIncomplete(AppError):
    """That person's profile is not complete enough to connect with."""

    status_code = 422
    code = "receiver_profile_incomplete"

    def __init__(self) -> None:
        super().__init__(
            "That person's profile is not complete enough to connect with.",
            fields={"receiver_id": "This person has not finished their profile yet."},
        )


class ConnectionNotEstablished(Forbidden):
    """A conversation opens only when both people have accepted."""

    code = "connection_not_established"


class NotReceiver(Forbidden):
    """Only the person who received the request can respond to it."""

    code = "not_receiver"


class NotSender(Forbidden):
    """Only the person who sent the request can withdraw it."""

    code = "not_sender"


class NotIdeaOwner(Forbidden):
    """You can only edit your own ideas."""

    code = "not_idea_owner"


class IdeaClosed(Conflict):
    """This idea is no longer open."""

    code = "idea_closed"


class LastAdmin(Conflict):
    """You cannot remove the last admin."""

    code = "last_admin"


class InUseConflict(Conflict):
    code = "skill_in_use"
    """That is in use. Rename it instead."""


def error_body(code: str, message: str, fields: dict | None = None) -> dict:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if fields:
        body["error"]["fields"] = fields
    return body


async def app_error_handler(_request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message, exc.fields),
    )


async def http_error_handler(_request, exc: HTTPException) -> JSONResponse:
    """Make FastAPI's own 401/403/404 conform to the standard shape."""
    code = {
        401: "unauthenticated",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        413: "file_too_large",
    }.get(exc.status_code, "error")
    detail = exc.detail if isinstance(exc.detail, str) else "Something went wrong."
    return JSONResponse(status_code=exc.status_code, content=error_body(code, detail))


async def validation_error_handler(_request, exc) -> JSONResponse:
    """Pydantic errors -> 422 with a `fields` map keyed by request field name."""
    fields: dict[str, str] = {}
    for err in exc.errors():
        loc = err.get("loc") or ()
        field = str(loc[-1]) if loc else "request"
        fields[field] = err.get("msg", "Invalid value.")
    return JSONResponse(
        status_code=422,
        content=error_body("validation_error", "Some fields need attention.", fields),
    )