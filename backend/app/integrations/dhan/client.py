"""Small async wrapper around the synchronous DhanHQ Python SDK."""

import os
from functools import lru_cache
from typing import Any, Dict, Optional

from dhanhq import DhanContext, dhanhq
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.utils.logger import get_logger
from app.integrations.dhan.auth import get_access_token

logger = get_logger(__name__)

BUY = dhanhq.BUY
SELL = dhanhq.SELL
MARKET = dhanhq.MARKET
LIMIT = dhanhq.LIMIT
INTRADAY = dhanhq.INTRA
DELIVERY = dhanhq.CNC
NSE_EQ = dhanhq.NSE


from dhanhq import DhanContext, dhanhq

# client_id    = "{{CLIENT_ID}}"
# access_token = "{{ACCESS_TOKEN}}"

# dhan = dhanhq(DhanContext(client_id, access_token))

class DhanAPIError(Exception):
    """Normalized Dhan SDK/API error."""


def is_dhan_configured() -> bool:
    return bool(
        settings.dhan_client_id and
        settings.dhan_access_token
    )

@lru_cache(maxsize=1)
def get_dhan_context() -> DhanContext:
    if not is_dhan_configured():
        raise DhanAPIError(
            "DhanHQ credentials not configured. Set DHAN_CLIENT_ID and "
            "DHAN_ACCESS_TOKEN in backend/.env."
        )
    return DhanContext(
        settings.dhan_client_id,
        settings.dhan_access_token,
        # get_access_token()
        )


@lru_cache(maxsize=1)
def get_dhan_client() -> dhanhq:
    return dhanhq(get_dhan_context())


async def _call(method_name: str, *args: Any, **kwargs: Any) -> Any:
    """Run a blocking SDK method without blocking FastAPI's event loop."""
    try:
        client = get_dhan_client()
        method = getattr(client, method_name)
        response = await run_in_threadpool(method, *args, **kwargs)
    except Exception as exc:
        logger.error("DhanHQ %s failed: %s", method_name, exc)
        raise DhanAPIError(f"DhanHQ '{method_name}' failed: {exc}") from exc

    if isinstance(response, dict) and str(response.get("status", "")).lower() == "failure":
        message = response.get("remarks") or response.get("message") or response.get("data") or response
        raise DhanAPIError(f"DhanHQ '{method_name}' returned failure: {message}")

    return response


async def place_order_raw(**kwargs: Any) -> Any:
    return await _call("place_order", **kwargs)


async def get_holdings_raw() -> Any:
    return await _call("get_holdings")


async def get_positions_raw() -> Any:
    return await _call("get_positions")


async def get_fund_limits_raw() -> Any:
    return await _call("get_fund_limits")


async def get_order_list_raw() -> Any:
    return await _call("get_order_list")


async def get_order_by_id_raw(order_id: str) -> Any:
    return await _call("get_order_by_id", order_id)


async def cancel_order_raw(order_id: str) -> Any:
    return await _call("cancel_order", order_id)


async def modify_order_raw(order_id: str, **kwargs: Any) -> Any:
    return await _call("modify_order", order_id, **kwargs)


_security_master: Optional[Dict[str, Dict[str, str]]] = None


def _normalise_symbol(symbol: str) -> str:
    return symbol.upper().replace(".NS", "").replace(".BO", "").strip()


async def resolve_security_id(symbol: str) -> Optional[str]:
    """Resolve a user-facing symbol to Dhan's security ID."""
    global _security_master

    if _security_master is None:
        await refresh_security_master()

    row = _security_master.get(_normalise_symbol(symbol)) if _security_master else None
    return row["security_id"] if row else None


async def refresh_security_master() -> int:
    """Load Dhan's compact security master into memory."""
    global _security_master

    raw = await _call("fetch_security_list", "compact")
    rows = raw if isinstance(raw, list) else raw.get("data", []) if isinstance(raw, dict) else []

    cache: Dict[str, Dict[str, str]] = {}
    for row in rows:
        symbol = str(row.get("SEM_TRADING_SYMBOL") or row.get("symbol") or "").upper().strip()
        security_id = row.get("SEM_SMST_SECURITY_ID") or row.get("security_id")
        if symbol and security_id:
            cache[symbol] = {
                "security_id": str(security_id),
                "exchange": str(row.get("SEM_EXM_EXCH_ID") or row.get("exchange") or ""),
            }

    _security_master = cache
    logger.info("Dhan security master loaded: %s symbols", len(cache))
    return len(cache)


def get_security_master() -> list[dict]:
    """Return the currently cached security master rows in a frontend-friendly shape."""
    if not _security_master:
        return []
    return [
        {"symbol": symbol, **data}
        for symbol, data in sorted(_security_master.items())
    ]

# wherever refresh_security_master() currently is
# from app.services.security_master_index import security_index

# async def refresh_security_master() -> int:
#     raw_rows = await _fetch_security_master_from_dhan()  # your existing fetch logic
#     _cache_security_master(raw_rows)                      # your existing cache set
#     count = security_index.build(raw_rows)                # NEW: build the fuzzy index
#     return count