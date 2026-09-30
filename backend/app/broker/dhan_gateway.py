"""The only module that imports the DhanHQ SDK.

Callers ask for balances, positions, orders, security ids, and candles.
They do not construct a `dhanhq` client themselves.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

import pandas as pd
from dhanhq import dhanhq
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

NSE_EQUITY = dhanhq.NSE
BUY = dhanhq.BUY
SELL = dhanhq.SELL
MARKET = dhanhq.MARKET
INTRADAY = dhanhq.INTRA


class DhanRequestError(Exception):
    """The DhanHQ SDK call failed or returned a failure status."""


def is_dhan_configured() -> bool:
    """True when both the client id and the access token are set."""
    return bool(settings.dhan_client_id and settings.dhan_access_token)


@lru_cache(maxsize=1)
def _sdk_client() -> dhanhq:
    if not is_dhan_configured():
        raise DhanRequestError(
            "DhanHQ credentials are not configured. Set DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN."
        )
    return dhanhq(settings.dhan_client_id, settings.dhan_access_token)


async def _call(method_name: str, *args: Any, **kwargs: Any) -> Any:
    """Run one blocking SDK method off the event loop and reject failure payloads."""
    try:
        method = getattr(_sdk_client(), method_name)
        response = await run_in_threadpool(method, *args, **kwargs)
    except DhanRequestError:
        raise
    except Exception as exc:
        logger.error("DhanHQ %s failed: %s", method_name, exc)
        raise DhanRequestError(f"DhanHQ '{method_name}' failed: {exc}") from exc

    if isinstance(response, dict) and str(response.get("status", "")).lower() == "failure":
        message = response.get("remarks") or response.get("message") or response.get("data") or response
        raise DhanRequestError(f"DhanHQ '{method_name}' returned failure: {message}")
    return response


def _payload(response: Any) -> Any:
    if isinstance(response, dict) and "data" in response:
        return response["data"]
    return response


def _first(row: dict, *keys: str, default: Any = None) -> Any:
    for key in keys:
        if row.get(key) is not None:
            return row[key]
    return default


async def get_available_balance_inr() -> float:
    """Spendable cash in INR from the Dhan fund-limit endpoint."""
    payload = _payload(await _call("get_fund_limits"))
    if not isinstance(payload, dict):
        raise DhanRequestError("DhanHQ fund limits did not return an object.")
    # Dhan's payload spells this field 'availabelBalance'.
    raw = _first(payload, "availabelBalance", "availableBalance", default=0)
    return float(raw or 0)


async def get_intraday_positions() -> list[dict]:
    """Open NSE intraday positions.

    Quantity is signed: positive is long, negative is short. Delivery
    positions are left out so this loop cannot flatten holdings it did
    not open as MIS.
    """
    payload = _payload(await _call("get_positions"))
    rows = payload if isinstance(payload, list) else []
    positions = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not _is_intraday(row):
            continue
        quantity = int(float(_first(row, "netQty", "net_qty", default=0) or 0))
        if quantity == 0:
            continue
        average = float(_first(row, "costPrice", "buyAvg", "averagePrice", default=0) or 0)
        last_price = float(_first(row, "lastTradedPrice", "ltp", default=0) or 0) or average
        positions.append(
            {
                "symbol": str(_first(row, "tradingSymbol", "trading_symbol", default="")).upper(),
                "security_id": str(_first(row, "securityId", "security_id", default="")),
                "quantity": quantity,
                "average_price": average,
                "last_price": last_price,
                "realized_pnl_inr": float(_first(row, "realizedProfit", "realized_profit", default=0) or 0),
                "product_type": "INTRADAY",
            }
        )
    return positions


async def get_realized_pnl_today_inr() -> float:
    """Realized intraday profit still reported by Dhan, in INR.

    Flat rows are included. A squared-off loss has net quantity zero, and
    dropping those rows would hide it from the daily loss halt.
    """
    payload = _payload(await _call("get_positions"))
    rows = payload if isinstance(payload, list) else []
    total = 0.0
    for row in rows:
        if isinstance(row, dict) and _is_intraday(row):
            total += float(_first(row, "realizedProfit", "realized_profit", default=0) or 0)
    return total


def _is_intraday(row: dict) -> bool:
    product = str(_first(row, "productType", "product_type", default="")).upper()
    return product in {"INTRADAY", "INTRA", "MIS"}


async def get_orders() -> list[dict]:
    """Today's Dhan orders, newest fields kept in a stable shape."""
    payload = _payload(await _call("get_order_list"))
    rows = payload if isinstance(payload, list) else []
    orders = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        orders.append(
            {
                "order_id": str(_first(row, "orderId", "order_id", default="")),
                "symbol": str(_first(row, "tradingSymbol", "trading_symbol", default="")),
                "side": str(_first(row, "transactionType", "transaction_type", default="")),
                "quantity": int(float(_first(row, "quantity", default=0) or 0)),
                "price": float(_first(row, "price", "averageTradedPrice", default=0) or 0),
                "status": str(_first(row, "orderStatus", "order_status", default="")),
                "product_type": str(_first(row, "productType", "product_type", default="")),
                "broker": "dhan",
            }
        )
    return orders


async def cancel_order(order_id: str) -> dict:
    """Ask Dhan to cancel one working order. Filled orders cannot be cancelled."""
    response = await _call("cancel_order", order_id)
    return {"order_id": order_id, "broker": "dhan", "response": response}


async def place_intraday_market_order(
    security_id: str,
    side: str,
    quantity: int,
) -> dict:
    """Place one NSE intraday market order. `side` is BUY or SELL. Quantity is shares."""
    if side not in {"BUY", "SELL"}:
        raise DhanRequestError("side must be BUY or SELL")
    if quantity <= 0:
        raise DhanRequestError("quantity must be greater than 0")

    response = await _call(
        "place_order",
        security_id=security_id,
        exchange_segment=NSE_EQUITY,
        transaction_type=BUY if side == "BUY" else SELL,
        quantity=int(quantity),
        order_type=MARKET,
        product_type=INTRADAY,
        price=0,
    )
    payload = _payload(response)
    order_id = ""
    if isinstance(payload, dict):
        order_id = str(_first(payload, "orderId", "order_id", default="") or "")
    return {
        "order_id": order_id,
        "status": "PLACED",
        "broker": "dhan",
        "response": response,
    }


_security_ids: dict[str, str] | None = None


async def resolve_security_id(symbol: str) -> str | None:
    """Map an NSE trading symbol to Dhan's security id, or None when it is absent."""
    global _security_ids
    if _security_ids is None:
        _security_ids = await _load_security_ids()
    return _security_ids.get(symbol.upper().replace(".NS", "").replace(".BO", "").strip())


async def _load_security_ids() -> dict[str, str]:
    """Load the compact NSE equity master. The SDK writes a CSV; it is kept in a temp dir."""

    def _fetch() -> Any:
        with tempfile.TemporaryDirectory() as directory:
            filename = f"{directory}/security_id_list.csv"
            return _sdk_client().fetch_security_list("compact", filename)

    frame = await run_in_threadpool(_fetch)
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        raise DhanRequestError("DhanHQ security master came back empty.")

    exchange = frame["SEM_EXM_EXCH_ID"].astype(str) if "SEM_EXM_EXCH_ID" in frame.columns else ""
    segment = frame["SEM_SEGMENT"].astype(str) if "SEM_SEGMENT" in frame.columns else ""
    equity = frame[(exchange == "NSE") & (segment == "E")]
    mapping: dict[str, str] = {}
    for _, row in equity.iterrows():
        symbol = str(row.get("SEM_TRADING_SYMBOL") or "").upper().strip()
        security_id = row.get("SEM_SMST_SECURITY_ID")
        if symbol and security_id is not None and str(security_id) != "nan":
            mapping[symbol] = str(security_id)
    logger.info("Dhan security master loaded: %s NSE equity symbols", len(mapping))
    return mapping


async def fetch_intraday_candles(symbol: str, security_id: str) -> pd.DataFrame | None:
    """15-minute OHLCV for the last week, in INR and share volume.

    Returns None when Dhan has no bars for this symbol. Columns are
    open, high, low, close, volume.
    """
    to_date = datetime.now()
    from_date = to_date - timedelta(days=7)
    response = await _call(
        "intraday_minute_data",
        security_id=security_id,
        exchange_segment=NSE_EQUITY,
        instrument_type="EQUITY",
        from_date=from_date.strftime("%Y-%m-%d"),
        to_date=to_date.strftime("%Y-%m-%d"),
        interval=15,
    )
    payload = _payload(response)
    if not isinstance(payload, dict) or not payload.get("close"):
        return None
    frame = pd.DataFrame(
        {
            "open": payload["open"],
            "high": payload["high"],
            "low": payload["low"],
            "close": payload["close"],
            "volume": payload["volume"],
        }
    )
    if frame.empty:
        return None
    return frame
