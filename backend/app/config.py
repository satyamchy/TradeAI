"""Application settings loaded from environment / .env."""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    app_name: str = "TradeX"
    app_env: str = "development"
    app_debug: bool = True
    api_version_prefix: str = "/api/v1"

    # PostgreSQL / Supabase. Keep credentials in .env, never in source code.
    database_url: str = ""

    # DhanHQ
    dhan_api_url: str = "https://api.dhan.co/v2"
    dhan_client_id: str = ""
    dhan_access_token: str = ""
    dhan_app_id: str = ""
    dhan_app_secret: str = ""
    dhan_pin: str = ""
    dhan_totp_secret: str = ""

    # LLM
    groq_api_key: str = ""

    # Server
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
