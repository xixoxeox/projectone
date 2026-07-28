from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    api_base_path: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://screener:screener@localhost:5432/screener"
    jwt_signing_key: str = Field(
        default="development-only-signing-key-change-me-32-chars", min_length=32
    )
    jwt_issuer: str = "swing-trading-screener"
    jwt_audience: str = "swing-trading-screener-web"
    jwt_access_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    refresh_token_pepper: str = Field(
        default="development-only-refresh-pepper-change-me", min_length=32
    )
    refresh_ttl_days: int = Field(default=14, ge=1, le=30)
    refresh_cookie_secure: bool = False
    cors_origins: list[str] = ["http://localhost:3000"]
    market_data_provider: Literal["toss"] = "toss"
    toss_api_base_url: str = "https://openapi.tossinvest.com"
    toss_client_id: str | None = None
    toss_client_secret: SecretStr | None = None
    toss_request_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    toss_max_retries: int = Field(default=2, ge=0, le=5)
    toss_token_expiry_skew_seconds: int = Field(default=30, ge=0, le=300)
    scheduler_enabled: bool = False
    watchlist_pipeline_hour: int = Field(default=18, ge=0, le=23)
    watchlist_pipeline_minute: int = Field(default=10, ge=0, le=59)
    pipeline_stale_after_minutes: int = Field(default=60, ge=1, le=1440)
    sync_history_years: int = Field(default=3, ge=1, le=20)
    sync_batch_size: int = Field(default=500, ge=10, le=5000)
    notification_enabled: bool = False
    notification_provider: Literal["slack"] = "slack"
    slack_webhook_url: SecretStr | None = None
    slack_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    slack_max_retries: int = Field(default=3, ge=1, le=3)

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.app_env == "production" and "development-only" in (
            self.jwt_signing_key + self.refresh_token_pepper
        ):
            raise ValueError("Production authentication secrets must be explicitly configured")
        if self.app_env == "production" and (
            not self.toss_client_id or not self.toss_client_secret
        ):
            raise ValueError("TOSS_CLIENT_ID and TOSS_CLIENT_SECRET are required in production")
        if self.notification_enabled and self.notification_provider == "slack":
            if self.slack_webhook_url is None:
                raise ValueError(
                    "SLACK_WEBHOOK_URL is required when Slack notifications are enabled"
                )
            url = self.slack_webhook_url.get_secret_value()
            if not url.startswith("https://hooks.slack.com/services/"):
                raise ValueError("SLACK_WEBHOOK_URL must be a Slack Incoming Webhook URL")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
