"""
yfinance implementation of FinancialDataProvider. This is the ONLY file
that should import yfinance directly — everything else in the app talks
to the Protocol, so swapping providers later means writing one new file
and changing one line in provider_factory.py.
"""

import asyncio

import yfinance as yf


class YFinanceProvider:
    async def get_quote(self, ticker: str) -> dict:
        return await asyncio.to_thread(self._get_quote_sync, ticker)

    async def get_historical_prices(self, ticker: str, period: str) -> dict:
        return await asyncio.to_thread(self._get_history_sync, ticker, period)

    async def get_company_profile(self, ticker: str) -> dict:
        return await asyncio.to_thread(self._get_profile_sync, ticker)

    def _get_quote_sync(self, ticker: str) -> dict:
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        return {
            "ticker": ticker.upper(),
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "currency": info.get("currency"),
            "pe_ratio": info.get("trailingPE"),
            "market_cap": info.get("marketCap"),
            "52_week_high": info.get("fiftyTwoWeekHigh"),
            "52_week_low": info.get("fiftyTwoWeekLow"),
        }

    def _get_history_sync(self, ticker: str, period: str) -> dict:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)
        if hist.empty:
            raise ValueError(f"No price data returned for ticker '{ticker}'.")
        return {
            "ticker": ticker.upper(),
            "period": period,
            "dates": [d.strftime("%Y-%m-%d") for d in hist.index],
            "close": [round(v, 2) for v in hist["Close"].tolist()],
            "volume": [int(v) for v in hist["Volume"].tolist()],
        }

    def _get_profile_sync(self, ticker: str) -> dict:
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        return {
            "ticker": ticker.upper(),
            "name": info.get("longName") or info.get("shortName") or ticker,
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "exchange": info.get("exchange"),
            "country": info.get("country"),
        }
