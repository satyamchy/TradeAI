"""
Unofficial NSE India API wrapper. Display/context use ONLY — do not feed
trade decisions from this source. No SLA, frequently blocks server IPs,
breaks without notice. Wrap every call defensively and always have a fallback.
"""

import logging
import httpx

logger = logging.getLogger(__name__)

_BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

_session: httpx.AsyncClient | None = None


async def _get_session() -> httpx.AsyncClient:
    global _session
    if _session is None:
        _session = httpx.AsyncClient(headers=_BASE_HEADERS, timeout=10.0)
        # NSE requires a homepage hit first to set session cookies
        try:
            await _session.get("https://www.nseindia.com")
        except Exception as e:
            logger.warning("NSE session warmup failed: %s", e)
    return _session


async def get_index_snapshot(index: str = "NIFTY 50") -> list[dict] | None:
    """Returns None on failure — caller MUST have a fallback, never raise into the request path."""
    try:
        session = await _get_session()
        resp = await session.get(
            "https://www.nseindia.com/api/equity-stockIndices",
            params={"index": index},
        )
        resp.raise_for_status()
        return resp.json().get("data", [])
    except Exception as e:
        logger.warning("NSE unofficial API failed for index=%s: %s", index, e)
        return None


async def get_top_gainers_losers(index: str = "NIFTY 50", top_n: int = 5) -> dict:
    data = await get_index_snapshot(index)
    if not data:
        return {"gainers": [], "losers": [], "source": "unavailable"}

    sorted_stocks = sorted(data, key=lambda x: x.get("pChange", 0), reverse=True)
    return {
        "gainers": sorted_stocks[:top_n],
        "losers": sorted_stocks[-top_n:][::-1],
        "source": "nse_unofficial",
    }