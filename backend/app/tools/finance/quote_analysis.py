"""
stock_analyzer tool — used by the conversational agent (app/api/conversation.py).

Previously this had its own yfinance-calling path (via a provider_factory/
FinancialDataProvider abstraction) with its own copy of RSI/MACD/etc. math
in app/calculations/finance_calcs.py — a second, parallel implementation of
exactly what app/services/market_data_service.py + technical_analysis_service.py
already do for the rest of the app (recommendation flow, /stocks/analyze,
the harness). That duplication is gone: this tool now calls the same two
services everything else calls, so there is exactly one place that talks to
yfinance and exactly one place that computes indicators.
"""

import logging

from app.services.company_resolver import resolve_ticker_symbol
from app.services.market_data_service import fetch_stock_market_data
from app.services.technical_analysis_service import run_technical_analysis

logger = logging.getLogger(__name__)

MANIFEST = {
    "name": "stock_analyzer",
    "description": "Fetch price history and compute technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands, support/resistance, volatility) for a stock ticker.",
    "input_schema": {
        "ticker": "stock ticker symbol or company name, e.g. 'TCS.NS' or 'Reliance'",
        "analysis_type": "optional — 'intraday' or 'delivery' (longer-horizon), defaults to 'delivery'",
    },
}


async def stock_analyzer(ticker: str, analysis_type: str = "delivery") -> dict:
    canonical = resolve_ticker_symbol(ticker)

    try:
        market_data = await fetch_stock_market_data(canonical)
        technicals = run_technical_analysis(market_data, analysis_type=analysis_type)
    except Exception as e:
        logger.exception("STOCK_ANALYZER_FAILED | ticker=%s", canonical)
        raise RuntimeError(f"stock_analyzer failed for ticker='{canonical}': {e}") from e

    quote = market_data.get("quote", {})
    fundamentals = market_data.get("fundamentals", {})
    history = market_data.get("history", [])

    return {
        "ticker": canonical,
        "name": quote.get("name") or canonical,
        "currency": quote.get("currency", "INR"),
        "current_price": quote.get("current_price"),
        "52_week_high": quote.get("52_week_high"),
        "52_week_low": quote.get("52_week_low"),
        "pe_ratio": fundamentals.get("pe_ratio"),
        "market_cap": fundamentals.get("market_cap"),
        "recent_closes": [c.get("close") for c in history[-5:]],
        "trend": technicals.get("trend"),
        "rsi_14": technicals.get("rsi_14"),
        "macd": technicals.get("macd"),
        "moving_averages": technicals.get("moving_averages"),
        "bollinger_bands": technicals.get("bollinger_bands"),
        "support_resistance": technicals.get("support_resistance"),
        "atr": technicals.get("atr"),
        "volume_analysis": technicals.get("volume_analysis"),
        "period_analyzed": analysis_type,
        "data_source": "yfinance",
    }
