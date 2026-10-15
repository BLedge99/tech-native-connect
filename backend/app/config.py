"""Application settings. Every env access in the app goes through here."""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://bootcamp:bootcamp@db:5432/bootcamp_connect"
    test_database_url: str = "postgresql+asyncpg://bootcamp:bootcamp@db:5432/bootcamp_connect_test"

    session_days: int = 7
    magic_link_minutes: int = 15

    mailpit_smtp_host: str = "mailpit"
    mailpit_smtp_port: int = 1025
    mailpit_web_url: str = "http://localhost:8025"
    mail_from: str = "no-reply@bootcampconnect.local"

    app_env: str = "development"
    cors_origins: str = "http://localhost:5173"

    # Where the BROWSER is. The API serves /api/v1, so anything it redirects to
    # or emails has to name the app's origin — a magic link minted against the
    # API port lands the user on a 404.
    app_url: str = "http://localhost:5173"

    # Spec 03 §4: hard cap, enforced at the request and the column.
    max_photo_bytes: int = 2 * 1024 * 1024
    max_bio_chars: int = 500
    max_looking_for_chars: int = 300
    max_display_name_chars: int = 80
    max_message_chars: int = 2000
    max_profile_skills: int = 20
    max_profile_interests: int = 20

    seed_admin_password: str = ""

    # Demo deployments have no mail provider, so the magic link cannot be
    # delivered. This returns it in the API response instead, and the sign-in
    # page renders it inline. Off everywhere by default: with it on, the
    # always-202 contract (auth.py) stops hiding which emails have accounts.
    # Real deployments set a mail provider and leave this false.
    demo_expose_magic_links: bool = False

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def require_secure_browser_origins_in_production(self) -> "Settings":
        """Refuse production URLs that would send auth links or cookies over HTTP."""
        if self.app_env == "production":
            if urlsplit(self.app_url).scheme != "https":
                raise ValueError("APP_URL must use HTTPS when APP_ENV=production")
            insecure_origins = [
                origin for origin in self.cors_origin_list
                if urlsplit(origin).scheme != "https"
            ]
            if insecure_origins:
                raise ValueError("CORS_ORIGINS must contain only HTTPS origins in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
