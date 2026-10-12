"""Request-size and response-header regressions for security boundaries."""

import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.anyio


async def test_chunked_photo_upload_is_rejected_before_multipart_parse(client, auth):
    signed_in = await auth()
    browser = signed_in["client"]
    boundary = "bootcamp-test-boundary"
    prefix = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="large.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode()
    suffix = f"\r\n--{boundary}--\r\n".encode()

    async def chunks():
        yield prefix
        for _ in range(17):
            yield b"x" * (128 * 1024)
        yield suffix

    response = await browser.post(
        "/api/v1/users/me/photo",
        content=chunks(),
        headers={
            **signed_in["csrf"],
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    await browser.aclose()

    assert response.status_code == 413, response.text
    assert response.json()["error"]["code"] == "file_too_large"


async def test_private_api_responses_are_not_cacheable(client):
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["x-frame-options"] == "DENY"


def test_production_rejects_http_browser_origins():
    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            app_url="http://app.example.test",
            cors_origins="https://app.example.test",
        )

    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            app_url="https://app.example.test",
            cors_origins="http://app.example.test",
        )
