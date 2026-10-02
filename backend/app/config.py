"""Application settings. Every env access in the app goes through here."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://bootcamp:bootcamp@db:5432/bootcamp_connect"
    test_database_url: str = "postgresql+asyncpg://bootcamp:bootcamp@db:5432/bootcamp_connect_test"

    session_secret: str = "dev-only-change-me"
    session_days: int = 7
    magic_link_minutes: int = 15

    mailpit_smtp_host: str = "mailpit"
    mailpit_smtp_port: int = 1025
    mailpit_web_url: str = "http://localhost:8025"
    mail_from: str = "no-reply@bootcampconnect.local"

    app_env: str = "development"
    cors_origins: str = "http://localhost:5173"

    # Spec 03 §4: hard cap, enforced at the request and the column.
    max_photo_bytes: int = 2 * 1024 * 1024
    max_bio_chars: int = 500
    max_looking_for_chars: int = 300
    max_display_name_chars: int = 80
    max_message_chars: int = 2000
    max_profile_skills: int = 20
    max_profile_interests: int = 20

    seed_admin_password: str = ""

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()