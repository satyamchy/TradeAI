"""
Provider interface for financial data. New data sources (Alpha Vantage,
a paid terminal API, etc.) implement this Protocol and get swapped in via
config — nothing above this layer (tools, agents, prompts) needs to change.
"""

from typing import Protocol


class FinancialDataProvider(Protocol):
    async def get_quote(self, ticker: str) -> dict:
        """Latest price, market cap, PE, 52w range."""
        ...

    async def get_historical_prices(self, ticker: str, period: str) -> dict:
        """OHLCV history for `period` (e.g. '6mo', '1y')."""
        ...

    async def get_company_profile(self, ticker: str) -> dict:
        """Name, sector, industry, exchange, currency."""
        ...
