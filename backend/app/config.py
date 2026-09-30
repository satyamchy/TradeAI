"""Environment settings.

Trading limits that the operator can change while the process is running
live on the automation runner, not here. Values in this module are the
defaults loaded at startup.
"""

from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    """Process configuration. Unknown environment keys are ignored."""

    app_name: str = "TradeX"
    app_env: str = "development"
    app_debug: bool = True
    api_version_prefix: str = "/api/v1"

    dhan_client_id: str = ""
    dhan_access_token: str = ""

    session_secret: str = "dev-session-secret-change-me"
    credentials_key: str = ""
    admin_username: str = "admin"
    admin_password: str = ""
    database_path: str = "tradex.db"
    frontend_origin: str = "http://localhost:5173"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # paper keeps orders off the exchange. live sends them through the DhanHQ SDK.
    trading_mode: str = "paper"
    paper_starting_balance_inr: float = 100_000.0
    paper_ledger_path: str = "paper_ledger.json"
    paper_ledger_dir: str = "paper_ledgers"

    max_positions: int = 4
    capital_per_trade_pct: float = 0.20
    cash_reserve_pct: float = 0.10
    take_profit_pct: float = 1.5
    stop_loss_pct: float = 1.0
    max_daily_loss_inr: float = 2_000.0
    cycle_interval_seconds: int = 180
    screener_limit: int = 6

    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings object."""
    return Settings()


settings = get_settings()
