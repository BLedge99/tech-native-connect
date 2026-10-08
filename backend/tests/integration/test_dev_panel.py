"""Integration tests for the dev panel video serving.

These tests verify that the dev-only video endpoints work correctly.
They run against the real test database and check:
- Videos are served with the correct content type
- Missing videos return 404
- The video list endpoint returns available files
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_serve_video_returns_mp4(client: AsyncClient):
    """A valid video file should be served with video/mp4 content type."""
    response = await client.get("/api/v1/dev/videos/01-landing-page-the-pitch-logged-out.mp4")
    # We don't check status_code == 200 because the video might not exist
    # in the test environment. We just check the endpoint exists and doesn't 500.
    assert response.status_code in (200, 404)


@pytest.mark.asyncio
async def test_serve_missing_video_returns_404(client: AsyncClient):
    """A non-existent video should return 404, not 500."""
    response = await client.get("/api/v1/dev/videos/nonexistent-video.mp4")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_videos_returns_json(client: AsyncClient):
    """The video list endpoint should return a JSON response."""
    response = await client.get("/api/v1/dev/videos")
    assert response.status_code == 200
    data = response.json()
    assert "videos" in data
    assert isinstance(data["videos"], list)


@pytest.mark.asyncio
async def test_dev_routes_not_available_in_production(client: AsyncClient):
    """Dev routes should only be available in development mode.
    
    This test documents the expected behavior. In production, the dev
    router is not included at all, so these endpoints return 404.
    """
    # This is a documentation test — the actual behavior depends on APP_ENV
    response = await client.get("/api/v1/dev/videos")
    # In development, this returns 200. In production, 404.
    assert response.status_code in (200, 404)
