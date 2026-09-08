import logging

import numpy as np

from app.calculations.finance_calcs import (
    calculate_rsi,
    calculate_sma,
    calculate_ema,
    calculate_volatility,
    calculate_period_return,
    calculate_macd,
    calculate_bollinger_bands,
    calculate_pivot_points,
    calculate_volume_trend,
    calculate_drawdown,
)
from app.tools.finance.provider_factory import get_provider

logger = logging.getLogger(__name__)

MANIFEST = {
    "name": "stock_analyzer",
    "description": "Fetch price history and compute complete technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands, Pivot Points, Volatility, Drawdown) for a stock ticker.",
    "input_schema": {
        "ticker": "stock ticker symbol, e.g. TCS.NS or AAPL",
        "period": "optional lookback window, e.g. '3mo', '6mo', '1y' — defaults to 6mo",
    },
}


async def stock_analyzer(ticker: str, period: str = "6mo") -> dict:
    provider = get_provider()

    try:
        history = await provider.get_historical_prices(ticker, period)
        quote = await provider.get_quote(ticker)
        profile = await provider.get_company_profile(ticker)
    except Exception as e:
        logger.exception("STOCK_ANALYZER_FAILED | ticker=%s period=%s", ticker, period)
        raise RuntimeError(f"stock_analyzer failed for ticker='{ticker}': {e}") from e

    closes = np.array(history.get("close", []))
    highs = history.get("high", [])
    lows = history.get("low", [])
    volumes = np.array(history.get("volume", []))

    # Calculate Pivot Points from recent high, low, close
    recent_high = max(highs[-5:]) if len(highs) >= 5 else (quote.get("52_week_high") or (closes[-1] if len(closes) > 0 else 0))
    recent_low = min(lows[-5:]) if len(lows) >= 5 else (quote.get("52_week_low") or (closes[-1] if len(closes) > 0 else 0))
    current_close = quote.get("current_price") or (closes[-1] if len(closes) > 0 else 0)

    pivots = calculate_pivot_points(high=recent_high, low=recent_low, close=current_close)

    indicators = {
        "sma_20": calculate_sma(closes, window=20),
        "sma_50": calculate_sma(closes, window=50),
        "ema_20": calculate_ema(closes, window=20),
        "rsi_14": calculate_rsi(closes, window=14),
        "macd": calculate_macd(closes),
        "bollinger_bands": calculate_bollinger_bands(closes, window=20),
        "pivot_points": pivots,
        "volume_trend_ratio": calculate_volume_trend(volumes, window=10) if len(volumes) > 0 else None,
        "max_drawdown_pct": calculate_drawdown(closes),
        "annualized_volatility_pct": calculate_volatility(closes),
        "period_return_pct": calculate_period_return(closes),
    }

    return {
        "ticker": ticker.upper(),
        "name": profile.get("name") or ticker.upper(),
        "currency": quote.get("currency", "INR"),
        "current_price": current_close,
        "52_week_high": quote.get("52_week_high"),
        "52_week_low": quote.get("52_week_low"),
        "pe_ratio": quote.get("pe_ratio"),
        "market_cap": quote.get("market_cap"),
        "recent_closes": history.get("close", [])[-5:],
        "indicators": indicators,
        "period_analyzed": period,
        "data_source": "yfinance",
    }

