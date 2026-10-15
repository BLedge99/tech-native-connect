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
    path = _inside(filename)
    if path is None:
        from app.errors import NotFound

        raise NotFound("No such video.")
    return FileResponse(path, media_type="video/mp4")


def _inside(filename: str) -> Path | None:
    """Resolve `filename` inside _VIDEOS_DIR, or None.

    Containment, not an `.exists()` on an un-resolved join. Starlette's path
    converter excludes `/` but not `\\`, so `..\\secret.txt` reaches this
    handler intact and joins straight out of the directory on Windows.

    The error is the standard envelope (specs/00_conventions.md §2) via NotFound,
    not an ad-hoc `{"error": "not_found"}` dict.
    """
    root = _VIDEOS_DIR.resolve()
    candidate = (root / filename).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    return candidate


@router.get("/videos")
async def list_videos():
    """List all available evidence videos."""
    if not _VIDEOS_DIR.exists():
        return {"videos": []}
    videos = sorted(
        f.name for f in _VIDEOS_DIR.iterdir() if f.suffix == ".mp4" and f.is_file()
    )
    return {"videos": videos}
