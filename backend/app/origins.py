"""Which browser origins the app trusts.

Shared by the WebSocket handshake check and the magic-link builder. A free
Cloudflare Quick Tunnel gets a new random `*.trycloudflare.com` host every time
it starts, so that suffix is trusted alongside the configured CORS origins.
"""

from __future__ import annotations

from urllib.parse import urlsplit


def is_allowed_origin(origin: str, allowed_origins: list[str]) -> bool:
    if "*" in allowed_origins or origin in allowed_origins:
        return True
    try:
        parts = urlsplit(origin)
        hostname = (parts.hostname or "").lower()
        if parts.scheme == "https" and hostname.endswith(".trycloudflare.com"):
            return True
        for allowed in allowed_origins:
            if allowed.startswith("*.") and hostname.endswith(allowed[1:].lower()):
                return True
            if allowed.startswith("https://*.") and hostname.endswith(allowed[len("https://*."):].lower()):
                return True
    except Exception:
        return False
    return False


def browser_base_url(origin: str | None, allowed_origins: list[str], fallback: str) -> str:
    """The origin the browser is actually on, if it is one we trust.

    Magic links must point back at the page the user is on. Behind a tunnel that
    is the tunnel URL, not APP_URL (localhost), which an outside device cannot
    reach. An untrusted or missing Origin falls back to APP_URL, so a forged
    header cannot make the server mint links to someone else's site.
    """
    if origin and is_allowed_origin(origin, allowed_origins) and "*" not in origin:
        return origin.rstrip("/")
    return fallback
