import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.environ.get("ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Lead Capture Platform"
    app_env: str = "development"
    debug: bool = True

    secret_key: str = "dev-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 30

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/leadcapture"

    rate_limit_per_minute_ip: int = 10
    rate_limit_per_minute_widget: int = 30

    geo_provider_a_url: str = "https://ipapi.co"
    geo_provider_b_url: str = "https://ipinfo.io"
    geo_request_timeout_seconds: int = 2

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""

    webhook_signing_secret: str = ""

    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
