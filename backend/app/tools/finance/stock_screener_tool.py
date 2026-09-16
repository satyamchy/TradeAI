"""
screen_stocks tool — used by the conversational agent.

Ranks against wider, more flexible criteria than
market_data_service.fetch_top_intraday_movers() (which is a fixed
momentum/volatility/volume composite for the intraday-movers use case).
This tool still fetches through market_data_service + technical_analysis_service
— no separate yfinance path — but keeps its own ranking criteria
(rsi_oversold, breakout, low_pe, etc.) since that logic doesn't belong in
the shared data-fetching services.
"""

import asyncio
import logging

from app.services.market_data_service import fetch_stock_market_data
from app.services.technical_analysis_service import run_technical_analysis

logger = logging.getLogger(__name__)

MANIFEST = {
    "name": "screen_stocks",
    "description": "Screen and rank stocks from the Indian equities universe based on criteria: 'momentum', 'rsi_oversold', 'rsi_overbought', 'breakout', 'low_pe', or 'volume_surge'.",
    "input_schema": {
        "criteria": "screening criteria: 'momentum', 'rsi_oversold', 'rsi_overbought', 'breakout', 'low_pe', 'volume_surge' — defaults to 'momentum'",
        "top_n": "number of top ranked stocks to return, e.g. 5 — defaults to 5",
    },
}

SCREENER_UNIVERSE = [
    "TCS.NS", "RELIANCE.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "SBIN.NS", "TATAMOTORS.NS", "BHARTIARTL.NS", "ITC.NS", "LT.NS",
    "AXISBANK.NS", "SUNPHARMA.NS", "WIPRO.NS", "HCLTECH.NS", "KOTAKBANK.NS",
]


async def _analyze_single_stock(ticker: str) -> dict | None:
    try:
        market_data = await fetch_stock_market_data(ticker, period="3mo")
        technicals = run_technical_analysis(market_data, analysis_type="delivery")

        quote = market_data.get("quote", {})
        fundamentals = market_data.get("fundamentals", {})
        current_price = quote.get("current_price")
        high_52w = quote.get("52_week_high") or current_price
        rvol = (technicals.get("volume_analysis") or {}).get("rvol") or 1.0
        macd = technicals.get("macd") or {}
        moving_avgs = technicals.get("moving_averages") or {}

        return {
            "symbol": ticker.replace(".NS", ""),
            "ticker": ticker,
            "current_price": current_price,
            "rsi_14": technicals.get("rsi_14"),
            "sma_20": moving_avgs.get("sma_20"),
            "sma_50": moving_avgs.get("sma_50"),
            "pe_ratio": fundamentals.get("pe_ratio"),
            "52_week_high": high_52w,
            "price_to_52w_high": round(current_price / high_52w, 2) if high_52w else 1.0,
            "period_return_pct": technicals.get("price_change_pct"),
            "volume_surge_ratio": rvol,
            "macd_histogram": macd.get("histogram"),
            "trend": technicals.get("trend"),
            "momentum_score": (technicals.get("price_change_pct") or 0) + (rvol * 10),
        }
    except Exception as e:
        logger.warning("SCREENER_SINGLE_FAIL | ticker=%s | error=%s", ticker, e)
        return None


async def screen_stocks(criteria: str = "momentum", top_n: int = 5) -> dict:
    criteria_clean = criteria.strip().lower()

    results = await asyncio.gather(*(_analyze_single_stock(t) for t in SCREENER_UNIVERSE))
    analyzed_stocks = [r for r in results if r is not None]

    if not analyzed_stocks:
        return {"criteria": criteria, "ranked_stocks": [], "error": "No stock data available for screening."}

    if criteria_clean == "rsi_oversold":
        sorted_stocks = sorted([s for s in analyzed_stocks if s["rsi_14"] is not None], key=lambda x: x["rsi_14"])
    elif criteria_clean == "rsi_overbought":
        sorted_stocks = sorted([s for s in analyzed_stocks if s["rsi_14"] is not None], key=lambda x: x["rsi_14"], reverse=True)
    elif criteria_clean == "breakout":
        sorted_stocks = sorted(analyzed_stocks, key=lambda x: (x["price_to_52w_high"], x["volume_surge_ratio"] or 0), reverse=True)
    elif criteria_clean == "low_pe":
        sorted_stocks = sorted([s for s in analyzed_stocks if s["pe_ratio"] and s["pe_ratio"] > 0], key=lambda x: x["pe_ratio"])
    elif criteria_clean == "volume_surge":
        sorted_stocks = sorted([s for s in analyzed_stocks if s["volume_surge_ratio"] is not None], key=lambda x: x["volume_surge_ratio"], reverse=True)
    else:
        sorted_stocks = sorted(analyzed_stocks, key=lambda x: (x["momentum_score"], x["period_return_pct"] or 0), reverse=True)

    ranked = []
    for idx, s in enumerate(sorted_stocks[:top_n], start=1):
        ranked.append({
            "rank": idx,
            "symbol": s["symbol"],
            "ticker": s["ticker"],
            "current_price": s["current_price"],
            "trend": s["trend"],
            "rsi_14": s["rsi_14"],
            "pe_ratio": s["pe_ratio"],
            "return_3mo_pct": s["period_return_pct"],
            "volume_surge_ratio": s["volume_surge_ratio"],
            "signal_summary": f"RSI: {s['rsi_14']} | Return: {s['period_return_pct']}% | Trend: {s['trend']}",
        })

    return {
        "screening_criteria": criteria_clean,
        "total_screened": len(analyzed_stocks),
        "top_ranked_count": len(ranked),
        "ranked_stocks": ranked,
        "data_source": "yfinance",
    }
