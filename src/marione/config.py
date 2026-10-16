"""Configuration read from the environment. Nothing runs at import time: call `load_settings()`."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    discord_token: str = Field(min_length=1)
    guild_id: int
    database_url: str = Field(min_length=1)

    # AI. Without a key the agent stays silent and everything else works.
    openrouter_api_key: str = ""
    agent_model: str = "anthropic/claude-haiku-4.5"
    agent_gate_model: str = "google/gemini-2.5-flash-lite"
    agent_fallback_models: str = ""  # comma separated
    agent_daily_budget_usd: float = Field(default=0.5, ge=0)
    agent_monthly_budget_usd: float = Field(default=10.0, ge=0)

    # Name of the private voice channel idle members are moved to.
    afk_channel_name: str = "il letto"
    port: int = 8080
    timezone: str = "Europe/Rome"
    migrations_dir: Path = _DEFAULT_MIGRATIONS

    @property
    def fallback_models(self) -> list[str]:
        return [m.strip() for m in self.agent_fallback_models.split(",") if m.strip()]

    @property
    def ai_enabled(self) -> bool:
        return bool(self.openrouter_api_key)


def load_settings() -> Settings:
    return Settings()  # required fields come from the environment
