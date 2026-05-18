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


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — safe to call from any layer."""
    return Settings()
