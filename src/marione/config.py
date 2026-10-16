"""Configuration read from the environment. Nothing runs at import time: call `load_settings()`."""

import os
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

    # The web page. Login is Discord OAuth: create an application at
    # https://discord.com/developers/applications, add PUBLIC_URL/auth/callback as a redirect.
    public_url: str = ""  # e.g. https://marione.up.railway.app
    discord_client_id: str = ""
    discord_client_secret: str = ""
    web_session_secret: str = ""  # long random string that signs the login cookie
    announce_channel_id: int = 0  # where web actions (a heist) are announced; 0 = system channel

    # Music: YouTube may refuse server addresses. The text of a cookies.txt and/or a proxy help.
    ytdlp_cookies: str = ""
    ytdlp_proxy: str = ""

    # During a deploy the old container is still in voice for a few seconds: two sessions of the
    # same bot fight over the connection and break it. The new one waits this long before joining.
    voice_start_delay: float = Field(
        default_factory=lambda: 25.0 if os.environ.get("RAILWAY_DEPLOYMENT_ID") else 0.0, ge=0
    )

    port: int = 8080
    timezone: str = "Europe/Rome"
    migrations_dir: Path = _DEFAULT_MIGRATIONS

    @property
    def fallback_models(self) -> list[str]:
        return [m.strip() for m in self.agent_fallback_models.split(",") if m.strip()]

    @property
    def oauth_ready(self) -> bool:
        return all(
            (
                self.public_url,
                self.discord_client_id,
                self.discord_client_secret,
                self.web_session_secret,
            )
        )

    @property
    def ai_enabled(self) -> bool:
        return bool(self.openrouter_api_key)


def load_settings() -> Settings:
    return Settings()  # required fields come from the environment
