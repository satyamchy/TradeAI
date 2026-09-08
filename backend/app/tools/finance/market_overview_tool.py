import logging
import asyncio
import numpy as np
from app.tools.finance.provider_factory import get_provider

logger = logging.getLogger(__name__)

MANIFEST = {
    "name": "get_market_overview",
    "description": "Fetch overall market condition, status (Bullish/Bearish/Neutral), major indices performance (NIFTY 50, SENSEX, Nifty Bank, Nifty IT), sector performance, top gainers, and top losers.",
    "input_schema": {},
}

INDEX_MAP = {
    "^NSEI": "NIFTY 50",
    "^BSESN": "SENSEX",
    "^NSEBANK": "NIFTY BANK",
    "^CNXIT": "NIFTY IT",
}

BASKET_STOCKS = [
    {"ticker": "RELIANCE.NS", "name": "Reliance Industries", "sector": "Energy"},
    {"ticker": "TCS.NS", "name": "TCS", "sector": "Information Technology"},
    {"ticker": "INFY.NS", "name": "Infosys", "sector": "Information Technology"},
    {"ticker": "HDFCBANK.NS", "name": "HDFC Bank", "sector": "Banking & Financials"},
    {"ticker": "ICICIBANK.NS", "name": "ICICI Bank", "sector": "Banking & Financials"},
    {"ticker": "SBIN.NS", "name": "State Bank of India", "sector": "Banking & Financials"},
    {"ticker": "TATAMOTORS.NS", "name": "Tata Motors", "sector": "Automobile"},
    {"ticker": "BHARTIARTL.NS", "name": "Bharti Airtel", "sector": "Telecom"},
    {"ticker": "ITC.NS", "name": "ITC Ltd", "sector": "FMCG"},
    {"ticker": "LT.NS", "name": "Larsen & Toubro", "sector": "Infrastructure"},
    {"ticker": "SUNPHARMA.NS", "name": "Sun Pharma", "sector": "Pharmaceuticals"},
    {"ticker": "WIPRO.NS", "name": "Wipro", "sector": "Information Technology"},
]


async def get_market_overview() -> dict:
    provider = get_provider()

    # 1. Fetch Index Quotes
    indices_res = []
    index_pct_changes = []

    for symbol, label in INDEX_MAP.items():
        try:
            quote = await provider.get_quote(symbol)
            current = quote.get("current_price") or 0.0
            prev_close = quote.get("previous_close") or current
            pct_change = round(((current - prev_close) / prev_close * 100), 2) if prev_close > 0 else 0.0
            
            indices_res.append({
                "symbol": symbol,
                "name": label,
                "current_price": current,
                "change_pct": pct_change,
                "currency": quote.get("currency", "INR"),
            })
            index_pct_changes.append(pct_change)
        except Exception as e:
            logger.warning("FAILED_INDEX_FETCH | symbol=%s | error=%s", symbol, e)
            indices_res.append({
                "symbol": symbol,
                "name": label,
                "current_price": None,
                "change_pct": None,
                "currency": "INR",
            })

    # Determine overall market sentiment status
    valid_changes = [c for c in index_pct_changes if c is not None]
    avg_change = float(np.mean(valid_changes)) if valid_changes else 0.0

    if avg_change >= 0.5:
        market_status = "Bullish"
    elif avg_change <= -0.5:
        market_status = "Bearish"
    else:
        market_status = "Neutral"

    # 2. Fetch Basket Stock Quotes to compute Gainers, Losers, and Sector Performance
    sector_changes = {}
    stock_performances = []

    for item in BASKET_STOCKS:
        try:
            quote = await provider.get_quote(item["ticker"])
            current = quote.get("current_price") or 0.0
            prev_close = quote.get("previous_close") or current
            pct_change = round(((current - prev_close) / prev_close * 100), 2) if prev_close > 0 else 0.0

            stock_info = {
                "symbol": item["ticker"].replace(".NS", ""),
                "ticker": item["ticker"],
                "name": item["name"],
                "sector": item["sector"],
                "price": current,
                "change_pct": pct_change,
            }
            stock_performances.append(stock_info)

            # Aggregate by Sector
            if item["sector"] not in sector_changes:
                sector_changes[item["sector"]] = []
            sector_changes[item["sector"]].append(pct_change)
        except Exception as e:
            logger.warning("FAILED_BASKET_FETCH | ticker=%s | error=%s", item["ticker"], e)

    # Calculate sector averages
    sectors_summary = []
    for sector, changes in sector_changes.items():
        if changes:
            sectors_summary.append({
                "sector": sector,
                "average_change_pct": round(float(np.mean(changes)), 2),
                "trend": "Bullish" if np.mean(changes) > 0.2 else ("Bearish" if np.mean(changes) < -0.2 else "Neutral")
            })

    # Sort gainers and losers
    sorted_stocks = sorted(stock_performances, key=lambda x: x["change_pct"], reverse=True)
    top_gainers = sorted_stocks[:3]
    top_losers = sorted_stocks[-3:][::-1]

    return {
        "market_status": market_status,
        "average_index_change_pct": round(avg_change, 2),
        "indices": indices_res,
        "sectors": sorted(sectors_summary, key=lambda x: x["average_change_pct"], reverse=True),
        "top_gainers": top_gainers,
        "top_losers": top_losers,
        "data_source": "yfinance",
    }
