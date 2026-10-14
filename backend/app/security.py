"""Small ASGI security boundary for API response headers and request sizes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi.responses import JSONResponse

from app.config import Settings
from app.errors import error_body

ASGIReceive = Callable[[], Awaitable[dict]]
ASGISend = Callable[[dict], Awaitable[None]]


class SecurityMiddleware:
    """Bound HTTP bodies and mark private API responses as sensitive.

    Content-Length is only an early rejection optimization. The receive wrapper
    also counts streamed/chunked request bodies, for which it may be absent.
    """

    def __init__(self, app, *, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: dict, receive: ASGIReceive, send: ASGISend) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        is_api = path.startswith("/api/v1/")
        is_photo_upload = path == "/api/v1/users/me/photo" and scope.get("method") == "POST"
        limit = self.settings.max_photo_bytes + 8 * 1024 if is_photo_upload else None
        response_started = False

        async def secure_send(message: dict) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                headers = list(message.get("headers", []))
                if is_api:
                    protected = {
                        b"cache-control",
                        b"x-content-type-options",
                        b"x-frame-options",
                        b"referrer-policy",
                        b"strict-transport-security",
                        b"content-security-policy",
                    }
                    headers = [(key, value) for key, value in headers if key.lower() not in protected]
                    headers.extend(
                        [
                            (b"cache-control", b"no-store"),
                            (b"x-content-type-options", b"nosniff"),
                            (b"x-frame-options", b"DENY"),
                            (b"referrer-policy", b"strict-origin-when-cross-origin"),
                            (
                                b"content-security-policy",
                                b"default-src 'none'; base-uri 'none'; frame-ancestors 'none'",
                            ),
                        ]
                    )
                    if self.settings.app_env == "production":
                        headers.append((b"strict-transport-security", b"max-age=31536000"))
                message = {**message, "headers": headers}
            await send(message)

        if is_photo_upload:
            assert limit is not None
            content_length = next(
                (value for key, value in scope.get("headers", []) if key.lower() == b"content-length"),
                None,
            )
            if content_length is not None:
                try:
                    declared_length = int(content_length)
                except ValueError:
                    declared_length = -1
                if declared_length > limit:
                    await self._too_large(scope, receive, secure_send)
                    return

        if is_photo_upload:
            # Read at most cap+1 before FastAPI invokes Starlette's multipart
            # parser. Raising from inside that parser is translated to a 400,
            # so enforce the cap at the ASGI boundary and only replay bounded
            # bodies to the application.
            body = bytearray()
            disconnected = False
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    disconnected = True
                    break
                chunk = message.get("body", b"")
                if len(body) + len(chunk) > limit:
                    await self._too_large(scope, receive, secure_send)
                    return
                body.extend(chunk)
                if not message.get("more_body", False):
                    break

            sent = False

            async def replay_receive() -> dict:
                nonlocal sent
                if disconnected:
                    return {"type": "http.disconnect"}
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return {"type": "http.disconnect"}

            await self.app(scope, replay_receive, secure_send)
            return

        await self.app(scope, receive, secure_send)

    async def _too_large(self, scope: dict, receive: ASGIReceive, send: ASGISend) -> None:
        response = JSONResponse(
            status_code=413,
            content=error_body("file_too_large", "The request body is too large."),
        )
        await response(scope, receive, send)
