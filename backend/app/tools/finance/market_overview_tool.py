"""
get_market_overview tool — used by the conversational agent.

Previously this re-implemented its own index list and basket-stock fetch
loop from scratch via the (now-removed) provider abstraction — duplicating
app/services/market_data_service.get_indian_indices_summary() and
fetch_top_intraday_movers(), which already fetch this exact data for the
market-status REST endpoints (app/api/market_routes.py). This tool now
just calls those two functions and derives gainers/losers/sector
performance from what fetch_top_intraday_movers() already computed.
"""

import logging
from collections import defaultdict

from app.services.market_data_service import get_indian_market_status, get_indian_indices_summary, fetch_top_intraday_movers

logger = logging.getLogger(__name__)

MANIFEST = {
    "name": "get_market_overview",
    "description": "Fetch overall market condition, status (Bullish/Bearish/Neutral), major indices performance, sector performance, top gainers, and top losers.",
    "input_schema": {},
}


async def get_market_overview() -> dict:
    status = get_indian_market_status()
    indices = await get_indian_indices_summary()

    valid_changes = [i["change_pct"] for i in indices if i.get("change_pct") is not None]
    avg_change = round(sum(valid_changes) / len(valid_changes), 2) if valid_changes else 0.0
    if avg_change >= 0.5:
        market_sentiment = "Bullish"
    elif avg_change <= -0.5:
        market_sentiment = "Bearish"
    else:
        market_sentiment = "Neutral"

    movers = await fetch_top_intraday_movers(top_n=25)  # whole basket, ranked

    sector_changes = defaultdict(list)
    for m in movers:
        sector_changes[m["sector"]].append(m["price_change_pct"])
    sectors = [
        {
            "sector": sector,
            "average_change_pct": round(sum(changes) / len(changes), 2),
            "trend": "Bullish" if sum(changes) / len(changes) > 0.2 else ("Bearish" if sum(changes) / len(changes) < -0.2 else "Neutral"),
        }
        for sector, changes in sector_changes.items()
    ]

    by_change = sorted(movers, key=lambda m: m["price_change_pct"], reverse=True)

    return {
        "market_status": status["status"],
        "market_sentiment": market_sentiment,
        "average_index_change_pct": avg_change,
        "indices": indices,
        "sectors": sorted(sectors, key=lambda s: s["average_change_pct"], reverse=True),
        "top_gainers": by_change[:3],
        "top_losers": by_change[-3:][::-1],
        "data_source": "yfinance",
    }
