import logging
import asyncio
import numpy as np

from app.calculations.finance_calcs import (
    calculate_rsi,
    calculate_sma,
    calculate_volatility,
    calculate_period_return,
    calculate_macd,
    calculate_volume_trend,
)
from app.tools.finance.provider_factory import get_provider

logger = logging.getLogger(__name__)

MANIFEST = {
    "name": "screen_stocks",
    "description": "Screen and rank stocks from the Indian equities universe (NIFTY 50 / BSE 100) based on criteria like 'momentum', 'rsi_oversold', 'rsi_overbought', 'breakout', 'low_pe', or 'volume_surge'.",
    "input_schema": {
        "criteria": "screening criteria: 'momentum', 'rsi_oversold', 'rsi_overbought', 'breakout', 'low_pe', 'volume_surge' — defaults to 'momentum'",
        "top_n": "number of top ranked stocks to return, e.g. 5 — defaults to 5",
    },
}

SCREENER_UNIVERSE = [
    {"ticker": "TCS.NS", "name": "Tata Consultancy Services"},
    {"ticker": "RELIANCE.NS", "name": "Reliance Industries"},
    {"ticker": "INFY.NS", "name": "Infosys"},
    {"ticker": "HDFCBANK.NS", "name": "HDFC Bank"},
    {"ticker": "ICICIBANK.NS", "name": "ICICI Bank"},
    {"ticker": "SBIN.NS", "name": "State Bank of India"},
    {"ticker": "TATAMOTORS.NS", "name": "Tata Motors"},
    {"ticker": "BHARTIARTL.NS", "name": "Bharti Airtel"},
    {"ticker": "ITC.NS", "name": "ITC Ltd"},
    {"ticker": "LT.NS", "name": "Larsen & Toubro"},
    {"ticker": "AXISBANK.NS", "name": "Axis Bank"},
    {"ticker": "SUNPHARMA.NS", "name": "Sun Pharma"},
    {"ticker": "WIPRO.NS", "name": "Wipro"},
    {"ticker": "HCLTECH.NS", "name": "HCL Technologies"},
    {"ticker": "KOTAKBANK.NS", "name": "Kotak Mahindra Bank"},
]


async def _analyze_single_stock(provider, stock: dict) -> dict | None:
    ticker = stock["ticker"]
    try:
        history = await provider.get_historical_prices(ticker, period="3mo")
        quote = await provider.get_quote(ticker)
        closes = np.array(history.get("close", []))
        volumes = np.array(history.get("volume", []))

        if len(closes) < 20:
            return None

        current_price = quote.get("current_price") or (closes[-1] if len(closes) > 0 else 0)
        rsi = calculate_rsi(closes, window=14)
        sma20 = calculate_sma(closes, window=20)
        sma50 = calculate_sma(closes, window=50)
        volatility = calculate_volatility(closes)
        period_return = calculate_period_return(closes)
        macd = calculate_macd(closes)
        volume_trend = calculate_volume_trend(volumes, window=10) if len(volumes) > 0 else 1.0

        pe_ratio = quote.get("pe_ratio")
        high_52w = quote.get("52_week_high") or current_price

        # Trend & Momentum indicators
        trend_status = "Strong Bullish" if (sma20 and sma50 and current_price > sma20 > sma50) else (
            "Bullish" if (sma20 and current_price > sma20) else "Neutral/Bearish"
        )
        momentum_score = (period_return or 0) + ((volume_trend or 1.0) * 10)

        return {
            "symbol": ticker.replace(".NS", ""),
            "ticker": ticker,
            "name": stock["name"],
            "current_price": current_price,
            "rsi_14": rsi,
            "sma_20": sma20,
            "sma_50": sma50,
            "pe_ratio": pe_ratio,
            "52_week_high": high_52w,
            "price_to_52w_high": round(current_price / high_52w, 2) if high_52w else 1.0,
            "period_return_pct": period_return,
            "volatility_pct": volatility,
            "volume_surge_ratio": volume_trend,
            "macd_histogram": macd.get("histogram") if macd else None,
            "trend": trend_status,
            "momentum_score": momentum_score,
        }
    except Exception as e:
        logger.warning("SCREENER_SINGLE_FAIL | ticker=%s | error=%s", ticker, e)
        return None


async def screen_stocks(criteria: str = "momentum", top_n: int = 5) -> dict:
    provider = get_provider()
    criteria_clean = criteria.strip().lower()

    tasks = [_analyze_single_stock(provider, s) for s in SCREENER_UNIVERSE]
    results = await asyncio.gather(*tasks)
    analyzed_stocks = [r for r in results if r is not None]

    if not analyzed_stocks:
        return {"criteria": criteria, "ranked_stocks": [], "error": "No stock data available for screening."}

    # Sorting & Filtering logic based on mathematical criteria
    if criteria_clean == "rsi_oversold":
        # Sort by lowest RSI
        sorted_stocks = sorted(
            [s for s in analyzed_stocks if s["rsi_14"] is not None],
            key=lambda x: x["rsi_14"],
        )
    elif criteria_clean == "rsi_overbought":
        # Sort by highest RSI
        sorted_stocks = sorted(
            [s for s in analyzed_stocks if s["rsi_14"] is not None],
            key=lambda x: x["rsi_14"],
            reverse=True,
        )
    elif criteria_clean == "breakout":
        # Sort by proximity to 52-week high & volume surge ratio
        sorted_stocks = sorted(
            analyzed_stocks,
            key=lambda x: (x["price_to_52w_high"], x["volume_surge_ratio"] or 0),
            reverse=True,
        )
    elif criteria_clean == "low_pe":
        # Sort by lowest valid P/E ratio > 0
        sorted_stocks = sorted(
            [s for s in analyzed_stocks if s["pe_ratio"] and s["pe_ratio"] > 0],
            key=lambda x: x["pe_ratio"],
        )
    elif criteria_clean == "volume_surge":
        # Sort by highest volume surge ratio
        sorted_stocks = sorted(
            [s for s in analyzed_stocks if s["volume_surge_ratio"] is not None],
            key=lambda x: x["volume_surge_ratio"],
            reverse=True,
        )
    else:
        # Default: Momentum ranking (highest period return & positive MACD)
        sorted_stocks = sorted(
            analyzed_stocks,
            key=lambda x: (x["momentum_score"], x["period_return_pct"] or 0),
            reverse=True,
        )

    # Format top_n ranked output
    ranked = []
    for idx, s in enumerate(sorted_stocks[:top_n], start=1):
        risk_level = "High" if (s["volatility_pct"] and s["volatility_pct"] > 35) else (
            "Medium" if (s["volatility_pct"] and s["volatility_pct"] > 20) else "Low"
        )
        ranked.append({
            "rank": idx,
            "symbol": s["symbol"],
            "ticker": s["ticker"],
            "name": s["name"],
            "current_price": s["current_price"],
            "trend": s["trend"],
            "rsi_14": s["rsi_14"],
            "pe_ratio": s["pe_ratio"],
            "return_3mo_pct": s["period_return_pct"],
            "volume_surge_ratio": s["volume_surge_ratio"],
            "risk_level": risk_level,
            "signal_summary": f"RSI: {s['rsi_14']} | 3Mo Return: {s['period_return_pct']}% | Trend: {s['trend']}",
        })

    return {
        "screening_criteria": criteria_clean,
        "total_screened": len(analyzed_stocks),
        "top_ranked_count": len(ranked),
        "ranked_stocks": ranked,
        "data_source": "yfinance",
    }
