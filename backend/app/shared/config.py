"""Central application settings with explicit development/live controls."""

from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    """Environment-backed settings. Unknown environment keys are ignored."""

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
    instrument_master_path: str = "data/instruments/nse_equity.csv"
    frontend_origin: str = "http://localhost:5173"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    analysis_quick_provider: str = "groq"
    analysis_quick_model: str = ""
    analysis_deep_provider: str = "groq"
    analysis_deep_model: str = ""
    tradingagents_data_dir: str = "data/tradingagents"

    trading_mode: str = "paper"
    live_trading_enabled: bool = False
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

    @property
    def live_execution_allowed(self) -> bool:
        """Live execution requires both mode selection and the explicit safety gate."""
        return (
            self.app_env.strip().lower() == "production"
            and self.trading_mode.strip().lower() == "live"
            and self.live_trading_enabled
        )

    def validate_runtime(self) -> None:
        """Fail closed on invalid production settings before the app starts."""
        if self.app_env.strip().lower() != "production":
            return
        if self.session_secret == "dev-session-secret-change-me" or len(self.session_secret) < 16:
            raise RuntimeError("Set a long SESSION_SECRET before APP_ENV=production")
        if not self.credentials_key:
            raise RuntimeError("Set CREDENTIALS_KEY before APP_ENV=production")
        if self.app_debug:
            raise RuntimeError("Set APP_DEBUG=false before APP_ENV=production")


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings object."""
    return Settings()


settings = get_settings()
