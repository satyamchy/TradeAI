"""The only module that imports the DhanHQ SDK.

Callers ask for balances, positions, orders, security ids, and candles.
They do not construct a `dhanhq` client themselves.
"""

from __future__ import annotations

import asyncio
import tempfile
from functools import lru_cache
from typing import Any

import pandas as pd
from dhanhq import dhanhq
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.trading.nse_session import now_ist
from app.utils.logger import get_logger

logger = get_logger(__name__)

NSE_EQUITY = dhanhq.NSE
BUY = dhanhq.BUY
SELL = dhanhq.SELL
MARKET = dhanhq.MARKET
INTRADAY = dhanhq.INTRA


class DhanRequestError(Exception):
    """The DhanHQ SDK call failed or returned a failure status."""


class CredentialsRequired(DhanRequestError):
    """Live account calls need the trader's own saved Dhan token."""


_TERMINAL = {"TRADED", "REJECTED", "CANCELLED", "EXPIRED"}
_WORKING = {"PENDING", "TRANSIT", "PART_TRADED", "OPEN"}


def clear_sdk_client() -> None:
    """Drop the cached process client after the access token is renewed."""
    _sdk_client.cache_clear()


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


async def _call(method_name: str, *args: Any, creds: tuple[str, str] | None = None, **kwargs: Any) -> Any:
    """Run one blocking SDK method off the event loop and reject failure payloads.

    `creds` is (client_id, access_token) for one user. Without it, the
    process-level Dhan settings are used for market data.
    """
    try:
        client = dhanhq(creds[0], creds[1]) if creds else _sdk_client()
        method = getattr(client, method_name)
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


async def get_available_balance_inr(creds: tuple[str, str] | None = None) -> float:
    """Spendable cash in INR from the Dhan fund-limit endpoint."""
    payload = _payload(await _call("get_fund_limits", creds=creds))
    if not isinstance(payload, dict):
        raise DhanRequestError("DhanHQ fund limits did not return an object.")
    # Dhan's payload spells this field 'availabelBalance'.
    raw = _first(payload, "availabelBalance", "availableBalance", default=0)
    return float(raw or 0)


def require_user_creds(creds: tuple[str, str] | None) -> tuple[str, str]:
    """Live funds, positions, holdings, and orders use this trader's token only."""
    if not creds or not creds[0] or not creds[1]:
        raise CredentialsRequired("Save this trader's Dhan client id and access token before live orders")
    return creds


async def get_intraday_positions(creds: tuple[str, str] | None = None) -> list[dict]:
    """Open positions. Intraday and delivery are both returned, tagged by product."""
    return await get_account_book(creds)


async def get_account_book(creds: tuple[str, str] | None = None) -> list[dict]:
    """Intraday net positions plus delivery quantity that can be sold.

    MIS rows stay `INTRADAY`. CNC day-nets and demat holdings become
    `DELIVERY`. A symbol is not given a second intraday row.
    """
    if creds is None and not is_dhan_configured():
        raise CredentialsRequired("Save this trader's Dhan client id and access token before live orders")
    payload = _payload(await _call("get_positions", creds=creds))
    rows = payload if isinstance(payload, list) else []
    book: dict[tuple[str, str], dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        product = "INTRADAY" if _is_intraday(row) else "DELIVERY" if _is_delivery(row) else ""
        if not product:
            continue
        quantity = int(float(_first(row, "netQty", "net_qty", default=0) or 0))
        if quantity == 0:
            continue
        symbol = str(_first(row, "tradingSymbol", "trading_symbol", default="")).upper()
        average = float(_first(row, "costPrice", "buyAvg", "averagePrice", default=0) or 0)
        last_price = float(_first(row, "lastTradedPrice", "ltp", default=0) or 0) or average
        book[(symbol, product)] = {
            "symbol": symbol,
            "security_id": normalize_security_id(_first(row, "securityId", "security_id", default="")) or "",
            "quantity": quantity,
            "average_price": average,
            "last_price": last_price,
            "realized_pnl_inr": float(_first(row, "realizedProfit", "realized_profit", default=0) or 0),
            "product_type": product,
            "available_qty": quantity if quantity > 0 else 0,
        }

    holdings = _payload(await _call("get_holdings", creds=creds))
    holding_rows = holdings if isinstance(holdings, list) else []
    for row in holding_rows:
        if not isinstance(row, dict):
            continue
        symbol = str(_first(row, "tradingSymbol", "trading_symbol", default="")).upper()
        if not symbol:
            continue
        available = int(float(_first(row, "availableQty", "available_qty", "totalQty", default=0) or 0))
        average = float(_first(row, "avgCostPrice", "averagePrice", "costPrice", default=0) or 0)
        last_price = float(_first(row, "lastTradedPrice", "ltp", default=0) or 0) or average
        key = (symbol, "DELIVERY")
        current = book.get(key)
        day_net = int(current["quantity"]) if current else 0
        sellable = max(available, 0) + (max(day_net, 0) if current and available else 0)
        if current and not available:
            sellable = day_net if day_net > 0 else 0
        if sellable == 0 and day_net == 0:
            continue
        quantity = sellable if sellable else day_net
        book[key] = {
            "symbol": symbol,
            "security_id": normalize_security_id(_first(row, "securityId", "security_id", default=""))
            or (current or {}).get("security_id")
            or "",
            "quantity": quantity,
            "average_price": average or float((current or {}).get("average_price") or 0),
            "last_price": last_price or float((current or {}).get("last_price") or 0),
            "realized_pnl_inr": float((current or {}).get("realized_pnl_inr") or 0),
            "product_type": "DELIVERY",
            "available_qty": quantity if quantity > 0 else 0,
        }
    return list(book.values())


async def get_realized_pnl_today_inr(creds: tuple[str, str] | None = None) -> float:
    """Realized intraday profit still reported by Dhan, in INR.

    Flat rows are included. A squared-off loss has net quantity zero, and
    dropping those rows would hide it from the daily loss halt.
    """
    payload = _payload(await _call("get_positions", creds=creds))
    rows = payload if isinstance(payload, list) else []
    total = 0.0
    for row in rows:
        if isinstance(row, dict) and _is_intraday(row):
            total += float(_first(row, "realizedProfit", "realized_profit", default=0) or 0)
    return total


def _is_intraday(row: dict) -> bool:
    product = str(_first(row, "productType", "product_type", default="")).upper()
    return product in {"INTRADAY", "INTRA", "MIS"}


def _is_delivery(row: dict) -> bool:
    product = str(_first(row, "productType", "product_type", default="")).upper()
    return product in {"CNC", "DELIVERY", "MARGIN"}


async def get_orders(creds: tuple[str, str] | None = None) -> list[dict]:
    """Today's Dhan orders, newest fields kept in a stable shape."""
    payload = _payload(await _call("get_order_list", creds=creds))
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


async def cancel_order(order_id: str, creds: tuple[str, str] | None = None) -> dict:
    """Ask Dhan to cancel one working order. Filled orders cannot be cancelled."""
    response = await _call("cancel_order", order_id, creds=creds)
    return {"order_id": order_id, "broker": "dhan", "response": response}


async def place_market_order(
    security_id: str,
    side: str,
    quantity: int,
    product_type: str = "INTRADAY",
    creds: tuple[str, str] | None = None,
    tag: str | None = None,
) -> dict:
    """Place one NSE market order and poll until it trades, rejects, or times out.

    `product_type` is INTRADAY or DELIVERY. DELIVERY is CNC. `tag` is the
    correlation id stored before this call. An empty order id stays unknown
    so the caller does not send a second one.
    """
    if side not in {"BUY", "SELL"}:
        raise DhanRequestError("side must be BUY or SELL")
    if quantity <= 0:
        raise DhanRequestError("quantity must be greater than 0")
    if product_type not in {"INTRADAY", "DELIVERY"}:
        raise DhanRequestError("product_type must be INTRADAY or DELIVERY")

    response = await _call(
        "place_order",
        security_id=normalize_security_id(security_id) or security_id,
        exchange_segment=NSE_EQUITY,
        transaction_type=BUY if side == "BUY" else SELL,
        quantity=int(quantity),
        order_type=MARKET,
        product_type=INTRADAY if product_type == "INTRADAY" else dhanhq.CNC,
        price=0,
        tag=tag,
        creds=creds,
    )
    return await _finish_placement(response, creds, tag)


async def place_stop_order(
    security_id: str,
    side: str,
    quantity: int,
    trigger_price: float,
    product_type: str = "INTRADAY",
    creds: tuple[str, str] | None = None,
    tag: str | None = None,
) -> dict:
    """Park a stop-market order at Dhan. `side` is the exit side."""
    if trigger_price <= 0 or quantity <= 0:
        raise DhanRequestError("stop trigger and quantity must be greater than 0")
    response = await _call(
        "place_order",
        security_id=normalize_security_id(security_id) or security_id,
        exchange_segment=NSE_EQUITY,
        transaction_type=BUY if side == "BUY" else SELL,
        quantity=int(quantity),
        order_type=dhanhq.SLM,
        product_type=INTRADAY if product_type == "INTRADAY" else dhanhq.CNC,
        price=0,
        trigger_price=round(float(trigger_price), 2),
        tag=tag,
        creds=creds,
    )
    payload = _payload(response)
    order_id = ""
    if isinstance(payload, dict):
        order_id = str(_first(payload, "orderId", "order_id", default="") or "")
    if not order_id:
        raise DhanRequestError("Dhan did not return a stop order id")
    return {"order_id": order_id, "status": "PENDING", "broker": "dhan", "trigger_price": trigger_price}


async def quote_prices(security_ids: dict[str, str], creds: tuple[str, str] | None = None) -> dict[str, float]:
    """Last traded price in INR, keyed by symbol.

    `security_ids` maps a symbol to a Dhan security id. Candle closes are
    not used. Symbols with no quote are omitted.
    """
    if not security_ids:
        return {}
    id_to_symbol: dict[str, str] = {}
    numeric: list[int] = []
    for symbol, security_id in security_ids.items():
        normalized = normalize_security_id(security_id)
        if not normalized:
            continue
        id_to_symbol[normalized] = symbol
        numeric.append(int(normalized))
    if not numeric:
        return {}
    response = await _call("quote_data", {"NSE_EQ": numeric}, creds=creds)
    payload = _payload(response)
    prices: dict[str, float] = {}
    if not isinstance(payload, dict):
        return prices
    books = payload.get("NSE_EQ") if isinstance(payload.get("NSE_EQ"), dict) else payload
    if not isinstance(books, dict):
        return prices
    for raw_id, packet in books.items():
        if not isinstance(packet, dict):
            continue
        last = _first(packet, "last_price", "lastPrice", "ltp", default=0)
        price = float(last or 0)
        symbol = id_to_symbol.get(normalize_security_id(raw_id) or "")
        if symbol and price > 0:
            prices[symbol] = price
    return prices


async def poll_order(order_id: str, creds: tuple[str, str] | None = None, tag: str | None = None) -> dict:
    """Read an order until it is terminal, or return the last working status."""
    last = {"order_id": order_id, "status": "UNKNOWN", "traded_quantity": 0, "broker": "dhan"}
    for _ in range(8):
        try:
            if order_id:
                response = await _call("get_order_by_id", order_id, creds=creds)
            elif tag:
                response = await _call("get_order_by_correlationID", tag, creds=creds)
            else:
                return last
        except DhanRequestError as exc:
            last["error"] = str(exc)
            await asyncio.sleep(0.4)
            continue
        parsed = _parse_order(response, order_id)
        last = parsed
        if parsed["status"] in _TERMINAL or parsed["status"] == "PART_TRADED":
            return parsed
        await asyncio.sleep(0.4)
    return last


async def find_order_by_tag(tag: str, creds: tuple[str, str] | None = None) -> dict:
    """Recover an order after a crash using the correlation id stored first."""
    response = await _call("get_order_by_correlationID", tag, creds=creds)
    return _parse_order(response, "")


def normalize_security_id(raw: Any) -> str | None:
    """Turn a master-file float such as 1234.0 into the id Dhan expects."""
    if raw is None:
        return None
    text = str(raw).strip()
    if text.lower() in {"", "nan", "none"}:
        return None
    try:
        return str(int(float(text)))
    except (TypeError, ValueError):
        return None


def _parse_order(response: Any, order_id: str) -> dict:
    payload = _payload(response)
    row = payload
    if isinstance(payload, list):
        row = payload[0] if payload else {}
    if not isinstance(row, dict):
        row = {}
    status = str(_first(row, "orderStatus", "order_status", default="") or "").upper()
    if not status:
        status = "UNKNOWN"
    found = str(_first(row, "orderId", "order_id", default="") or order_id)
    traded = int(float(_first(row, "filledQty", "tradedQuantity", "filled_qty", default=0) or 0))
    return {
        "order_id": found,
        "status": status,
        "traded_quantity": traded,
        "broker": "dhan",
        "symbol": str(_first(row, "tradingSymbol", "trading_symbol", default="") or ""),
        "side": str(_first(row, "transactionType", "transaction_type", default="") or ""),
        "average_price": float(_first(row, "averageTradedPrice", "price", default=0) or 0),
    }


async def _finish_placement(response: Any, creds: tuple[str, str] | None, tag: str | None) -> dict:
    payload = _payload(response)
    order_id = ""
    if isinstance(payload, dict):
        order_id = str(_first(payload, "orderId", "order_id", default="") or "")
    if not order_id:
        recovered = {"order_id": "", "status": "UNKNOWN", "traded_quantity": 0, "broker": "dhan"}
        if tag:
            try:
                recovered = await find_order_by_tag(tag, creds)
            except DhanRequestError:
                pass
        return recovered
    try:
        return await poll_order(order_id, creds, tag)
    except DhanRequestError as exc:
        return {"order_id": order_id, "status": "UNKNOWN", "traded_quantity": 0, "broker": "dhan", "error": str(exc)}


_security_ids: dict[str, str] | None = None
_security_ids_on: str | None = None


async def resolve_security_id(symbol: str, creds: tuple[str, str] | None = None) -> str | None:
    """Map an NSE trading symbol to Dhan's security id, or None when it is absent."""
    mapping = await security_master(creds)
    key = symbol.upper().replace(".NS", "").replace(".BO", "").strip()
    return mapping.get(key)


async def security_master(creds: tuple[str, str] | None = None) -> dict[str, str]:
    """NSE equity ids, refreshed once each IST date. A user's token is enough."""
    global _security_ids, _security_ids_on
    today = now_ist().date().isoformat()
    if _security_ids is None or _security_ids_on != today:
        _security_ids = await _load_security_ids(creds)
        _security_ids_on = today
    return _security_ids


async def _load_security_ids(creds: tuple[str, str] | None = None) -> dict[str, str]:
    """Load the compact NSE equity master. The SDK writes a CSV; it is kept in a temp dir."""

    def _fetch() -> Any:
        client = dhanhq(creds[0], creds[1]) if creds else _sdk_client()
        with tempfile.TemporaryDirectory() as directory:
            filename = f"{directory}/security_id_list.csv"
            return client.fetch_security_list("compact", filename)

    frame = await run_in_threadpool(_fetch)
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        raise DhanRequestError("DhanHQ security master came back empty.")

    exchange = frame["SEM_EXM_EXCH_ID"].astype(str) if "SEM_EXM_EXCH_ID" in frame.columns else ""
    segment = frame["SEM_SEGMENT"].astype(str) if "SEM_SEGMENT" in frame.columns else ""
    equity = frame[(exchange == "NSE") & (segment == "E")]
    mapping: dict[str, str] = {}
    for _, row in equity.iterrows():
        symbol = str(row.get("SEM_TRADING_SYMBOL") or "").upper().strip()
        security_id = normalize_security_id(row.get("SEM_SMST_SECURITY_ID"))
        if symbol and security_id:
            mapping[symbol] = security_id
    logger.info("Dhan security master loaded: %s NSE equity symbols", len(mapping))
    return mapping


async def fetch_intraday_candles(symbol: str, security_id: str) -> pd.DataFrame | None:
    """15-minute OHLCV for the last week, in INR and share volume.

    Returns None when Dhan has no bars for this symbol. Columns are
    open, high, low, close, volume.
    """
    to_date = now_ist()
    from_date = to_date.replace(hour=0, minute=0, second=0, microsecond=0)
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
