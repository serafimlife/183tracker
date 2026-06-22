"""Application settings loaded from environment variables.

Uses python-dotenv to load a local `.env` file, then pydantic-settings
for validation and typed access. Handlers and services should depend on
`Settings` (or individual values passed in at startup), not on `os.environ`.
"""

from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load `.env` before pydantic reads the process environment.
load_dotenv()


class Settings(BaseSettings):
    """Required and optional configuration for the bot process."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = Field(..., alias="BOT_TOKEN")
    database_url: str = Field(..., alias="DATABASE_URL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    # When set, FSM state is stored in Redis (required for multi-instance deployments).
    # Example: redis://localhost:6379/0
    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    # Comma-separated Telegram user IDs permitted to use the bot.
    # Empty string disables the allowlist (any user accepted — not recommended in production).
    allowed_user_ids: str = Field(default="", alias="ALLOWED_USER_IDS")

    def allowed_user_id_set(self) -> frozenset[int]:
        """Return parsed set of allowed Telegram user IDs (empty = no restriction)."""
        ids: set[int] = set()
        for part in self.allowed_user_ids.split(","):
            part = part.strip()
            if part.isdigit():
                ids.add(int(part))
        return frozenset(ids)


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — safe to call from any layer."""
    return Settings()
