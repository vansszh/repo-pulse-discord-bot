"""Runtime configuration loaded from environment variables / ``.env``.

Uses ``pydantic-settings`` so values are validated at startup. Missing required
values (like ``DISCORD_BOT_TOKEN``) raise a clear error before the bot ever
tries to connect to Discord.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All RepoPulse settings, sourced from environment variables / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Discord -------------------------------------------------------------
    discord_bot_token: str = Field(..., description="Bot token from the Discord Developer Portal.")
    discord_dev_guild_ids: str = Field(
        default="",
        description="Comma-separated guild IDs for instant dev-time slash-command sync.",
    )

    # --- GitHub --------------------------------------------------------------
    github_webhook_secret: str = Field(
        ...,
        description="Shared secret used to verify incoming GitHub webhook signatures.",
    )

    # --- Webhook server ------------------------------------------------------
    webhook_host: str = Field(default="0.0.0.0", description="Interface the FastAPI server binds to.")
    webhook_port: int = Field(default=8000, ge=1, le=65535)

    # --- Storage -------------------------------------------------------------
    database_path: Path = Field(
        default=Path("./data/repopulse.db"),
        description="Path to the SQLite database file.",
    )

    # --- Review reminders ----------------------------------------------------
    review_reminder_hours: int = Field(
        default=24,
        ge=1,
        description="Hours of inactivity before a PR is nudged with a review reminder.",
    )
    review_reminder_interval_minutes: int = Field(
        default=60,
        ge=1,
        description="How often the background task scans for stale PRs.",
    )

    # --- Logging -------------------------------------------------------------
    log_level: str = Field(default="INFO", description="Python logging level name.")

    # --- Validators ----------------------------------------------------------
    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, v: str) -> str:
        return v.upper()

    @property
    def dev_guild_id_list(self) -> list[int]:
        """Parsed list of dev guild IDs, empty when unset."""
        if not self.discord_dev_guild_ids.strip():
            return []
        return [int(x) for x in self.discord_dev_guild_ids.split(",") if x.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton ``Settings`` instance.

    Cached so every module sees the same configuration without re-parsing the
    environment on every import.
    """

    return Settings()  # type: ignore[call-arg]
