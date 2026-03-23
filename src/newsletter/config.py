"""Central configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Loads keys from `.env` or the process environment.

    Env var names are derived from field names (uppercased). Examples:
    `whatsapp_phone_number_id` -> `WHATSAPP_PHONE_NUMBER_ID`.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App (pydantic-settings maps field names to UPPER_SNAKE env keys)
    env: str = Field(default="development")  # ENV
    public_base_url: str = Field(default="http://127.0.0.1:8000")  # PUBLIC_BASE_URL
    port: int = Field(default=8000)  # PORT

    # WhatsApp Cloud API
    whatsapp_phone_number_id: str = Field(default="")
    whatsapp_access_token: str = Field(default="")
    whatsapp_app_secret: str = Field(default="")
    whatsapp_verify_token: str = Field(default="")

    # Single-user v0: E.164 of the owner
    user_whatsapp_e164: str = Field(default="")

    # LLM (OpenAI-compatible)
    openai_api_key: str = Field(default="")
    openai_base_url: str = Field(default="https://api.openai.com/v1")
    openai_model: str = Field(default="gpt-4o-mini")

    # Schedule (interpreted in `digest_timezone`)
    digest_local_hour: int = Field(default=8)
    digest_local_minute: int = Field(default=30)
    digest_timezone: str = Field(default="UTC")

    # SQLite file in working directory by default
    database_url: str = Field(default="sqlite:///./newsletter.sqlite3")

    # Optional: protect POST /internal/run-digest (header X-Trigger-Secret)
    trigger_secret: str = Field(default="")


@lru_cache
def get_settings() -> Settings:
    return Settings()
