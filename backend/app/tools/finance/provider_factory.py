"""
Single place that decides which provider is active. Swapping data
sources later = add a new provider file + change PROVIDER_NAME (or read
it from app.config / an env var) — nothing else changes.
"""

from app.tools.finance.provider_base import FinancialDataProvider
from app.tools.finance.yfinance_provider import YFinanceProvider

PROVIDER_NAME = "yfinance"  # move to app.config / env var when you add a 2nd provider


def get_provider() -> FinancialDataProvider:
    if PROVIDER_NAME == "yfinance":
        return YFinanceProvider()
    raise ValueError(f"Unknown financial data provider '{PROVIDER_NAME}'")
