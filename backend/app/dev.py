"""Dev-only routes. Serves evidence videos for the dev panel.

This module is only imported when APP_ENV=development. It mounts a static
file handler at /api/v1/dev/videos/ so the frontend can serve the Playwright
recordings without a separate file server.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/v1/dev", tags=["dev"])

# In Docker, the backend is mounted at /app and videos at /app/videos.
# Locally, the path is <project>/backend/app/dev.py → <project>/videos.
# We check both locations.
_VIDEOS_DIR = Path(__file__).resolve().parent.parent / "videos"
if not _VIDEOS_DIR.exists():
    _VIDEOS_DIR = Path(__file__).resolve().parent.parent.parent / "videos"


@router.get("/videos/{filename}")
async def serve_video(filename: str):
    """Serve a single evidence video by filename."""
    # Prevent path traversal — only serve files that exist in videos/
    file_path = _VIDEOS_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        return {"error": "not_found"}, 404
    return FileResponse(file_path, media_type="video/mp4")


@router.get("/videos")
async def list_videos():
    """List all available evidence videos."""
    if not _VIDEOS_DIR.exists():
        return {"videos": []}
    videos = sorted(
        f.name for f in _VIDEOS_DIR.iterdir() if f.suffix == ".mp4"
    )
    return {"videos": videos}
