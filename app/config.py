from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    google_places_api_key: str | None = Field(default=None, alias="GOOGLE_PLACES_API_KEY")
    google_timezone_api_key: str | None = Field(default=None, alias="GOOGLE_TIMEZONE_API_KEY")
    frontend_origin: str = Field(default="http://localhost:5173", alias="FRONTEND_ORIGIN")
    enable_google_provider: bool = Field(default=True, alias="ENABLE_GOOGLE_PROVIDER")
    rate_limit_max_requests: int = Field(default=80, alias="RATE_LIMIT_MAX_REQUESTS")
    rate_limit_window_seconds: int = Field(default=60, alias="RATE_LIMIT_WINDOW_SECONDS")
    swiss_ephe_path: str | None = Field(default=None, alias="SWISS_EPHE_PATH")
    database_url: str = Field(
        default=f"sqlite:///{(Path(__file__).resolve().parents[1] / 'data' / 'kundali.db').as_posix()}",
        alias="DATABASE_URL",
    )
    session_cookie_name: str = Field(default="kundali_session", alias="SESSION_COOKIE_NAME")
    session_duration_hours: int = Field(default=168, alias="SESSION_DURATION_HOURS")
    session_secure_cookie: bool = Field(default=False, alias="SESSION_SECURE_COOKIE")
    nominatim_user_agent: str = Field(
        default="kundali-web-app/0.1 (contact: local-dev)",
        alias="NOMINATIM_USER_AGENT",
    )

    @property
    def google_enabled(self) -> bool:
        return bool(
            self.enable_google_provider
            and self.google_places_api_key
            and self.google_timezone_api_key
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
