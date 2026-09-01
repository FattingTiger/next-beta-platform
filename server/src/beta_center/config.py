from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEVELOPMENT_SECRET_SENTINEL = "development-only-change-me-32-bytes"  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="BETA_",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./data/beta_center.db"
    storage_root: Path = Path("./data/storage")
    secret_key: SecretStr = SecretStr(DEVELOPMENT_SECRET_SENTINEL)
    public_base_url: str = "http://127.0.0.1:8088"
    cookie_secure: bool = False
    cookie_domain: str | None = None
    use_x_accel_redirect: bool = False
    allowed_hosts: list[str] = Field(default_factory=lambda: ["127.0.0.1", "localhost", "testserver"])
    trusted_proxy_networks: list[str] = Field(default_factory=lambda: ["127.0.0.1/32", "::1/128"])

    database_pool_size: int = Field(default=5, ge=1, le=20)
    database_max_overflow: int = Field(default=3, ge=0, le=20)
    database_pool_timeout_seconds: int = Field(default=10, ge=1, le=60)

    access_token_minutes: int = Field(default=15, ge=5, le=120)
    refresh_token_days: int = Field(default=30, ge=1, le=90)
    login_failure_limit: int = Field(default=5, ge=3, le=20)
    login_lock_minutes: int = Field(default=15, ge=1, le=120)
    login_rate_window_minutes: int = Field(default=15, ge=1, le=120)
    login_ip_failure_limit: int = Field(default=30, ge=5, le=500)
    login_identity_failure_limit: int = Field(default=10, ge=3, le=100)
    admin_reauth_minutes: int = Field(default=15, ge=5, le=60)
    admin_reauth_lock_minutes: int = Field(default=15, ge=1, le=120)
    admin_reauth_session_failure_limit: int = Field(default=5, ge=3, le=20)
    admin_reauth_user_failure_limit: int = Field(default=10, ge=3, le=100)
    admin_reauth_ip_failure_limit: int = Field(default=30, ge=5, le=500)
    password_change_lock_minutes: int = Field(default=15, ge=1, le=120)
    password_change_session_failure_limit: int = Field(default=5, ge=3, le=20)
    password_change_user_failure_limit: int = Field(default=10, ge=3, le=100)
    password_change_ip_failure_limit: int = Field(default=30, ge=5, le=500)

    max_apk_bytes: int = Field(default=512 * 1024 * 1024, ge=1024 * 1024)
    max_image_bytes: int = Field(default=10 * 1024 * 1024, ge=256 * 1024)
    max_bug_attachments: int = Field(default=5, ge=1, le=10)
    download_ticket_minutes: int = Field(default=10, ge=1, le=60)

    apksigner_path: str = "apksigner"
    aapt_path: str = "aapt"
    apk_tool_timeout_seconds: int = Field(default=90, ge=10, le=300)
    require_apk_tools: bool = True
    auto_create_schema: bool = True

    @model_validator(mode="after")
    def validate_production_security(self) -> Settings:
        secret = self.secret_key.get_secret_value()
        if self.environment == "production":
            if secret == DEVELOPMENT_SECRET_SENTINEL or len(secret) < 32:
                raise ValueError("production requires a unique secret key of at least 32 characters")
            if not self.cookie_secure:
                raise ValueError("production requires secure cookies")
            if self.auto_create_schema:
                raise ValueError("production must run explicit database migrations")
            if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
                raise ValueError("production requires PostgreSQL")
            if urlparse(self.public_base_url).scheme != "https":
                raise ValueError("production public URL must use HTTPS")
            if not self.allowed_hosts or "*" in self.allowed_hosts:
                raise ValueError("production requires an explicit allowed host list")
            if not self.use_x_accel_redirect:
                raise ValueError("production requires protected-file offload through X-Accel-Redirect")
        return self

    def ensure_runtime_directories(self) -> None:
        self.storage_root.mkdir(parents=True, exist_ok=True)
        if self.database_url.startswith("sqlite:///./"):
            Path(self.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
