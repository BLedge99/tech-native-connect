from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://bootcamp:bootcamp@localhost:5432/bootcamp_connect"
    session_secret: str = "development-only-change-me"
    app_env: str = "development"
    mailpit_smtp_host: str = "localhost"
    mailpit_smtp_port: int = 1025
    mailpit_web_url: str = "http://localhost:8025"
    cors_origins: str = "http://localhost:5173"
    admin_emails: str = ""
    seed_admin_password: str | None = None
    demo_seed_password: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()