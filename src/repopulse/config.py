from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Discord
    discord_bot_token: str = Field(...)
    discord_dev_guild_ids: str = Field(default="")

    # GitHub
    github_webhook_secret: str = Field(...)

    # Webhook server
    webhook_host: str = Field(default="0.0.0.0")
    webhook_port: int = Field(default=8000, ge=1, le=65535)

    # Storage
    database_path: Path = Field(default=Path("./data/repopulse.db"))

    # Review reminders
    review_reminder_hours: int = Field(default=24, ge=1)
    review_reminder_interval_minutes: int = Field(default=60, ge=1)

    # Logging
    log_level: str = Field(default="INFO")

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, v: str) -> str:
        return v.upper()

    @property
    def dev_guild_id_list(self) -> list[int]:
        if not self.discord_dev_guild_ids.strip():
            return []
        return [int(x) for x in self.discord_dev_guild_ids.split(",") if x.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
