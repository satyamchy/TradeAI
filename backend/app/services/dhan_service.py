"""Simple DhanHQ trading service.

This module is the single application-level entry point for Dhan operations.
API routes, the trading harness, and an AI agent can all call these functions.
The Dhan SDK itself lives in app.integrations.dhan.client.
"""

import datetime
import uuid
from typing import Any, Dict, Optional

from sqlalchemy.future import select

from app.db.base import AsyncSessionLocal
from app.db.models import StockTradeLog
from app.guardrails.trading_guardrails import (
    get_guardrail_settings,
    validate_trade_execution,
)
from app.integrations.dhan.client import (
    BUY,
    DELIVERY,
    INTRADAY,
    MARKET,
    NSE_EQ,
    SELL,
    DhanAPIError,
    get_fund_limits_raw,
    get_holdings_raw,
    get_order_by_id_raw,
    get_order_list_raw,
    cancel_order_raw,
    is_dhan_configured,
    place_order_raw,
    resolve_security_id,
)


def _warning(message: str, **extra: Any) -> Dict[str, Any]:
    """Return the common non-live/error response shape."""
    return {
        "status": "warning",
        "is_live": False,
        "broker": "DhanHQ",
        "endpoint": "dhanhq-sdk",
        "warning": message,
        **extra,
    }


def _extract_order_id(response: Any) -> Optional[str]:
    if not isinstance(response, dict):
        return None

    data = response.get("data")
    if isinstance(data, dict):
        order_id = data.get("orderId") or data.get("order_id")
        if order_id:
            return str(order_id)

    order_id = response.get("orderId") or response.get("order_id")
    return str(order_id) if order_id else None


async def place_order(
    symbol: str,
    trade_type: str,
    quantity: int,
    price: float,
    product_type: str = "INTRADAY",
    asset_category: str = "STOCK",
    stop_loss: Optional[float] = None,
    target_price: Optional[float] = None,
    notes: Optional[str] = None,
):
    """Validate and place one paper/live order, then save the trade log."""
    try:
        symbol = symbol.strip().upper()
        trade_type = trade_type.strip().upper()
        product_type = (product_type or "INTRADAY").strip().upper()
        asset_category = (asset_category or "STOCK").strip().upper()

        if trade_type not in {"BUY", "SELL"}:
            raise ValueError("trade_type must be BUY or SELL.")
        if quantity <= 0:
            raise ValueError("quantity must be greater than 0.")
        if price < 0:
            raise ValueError("price cannot be negative.")

        allowed, reason = await validate_trade_execution(
            symbol=symbol,
            trade_type=trade_type,
            price=price,
            quantity=quantity,
        )
        if not allowed:
            raise ValueError(reason)

        settings = await get_guardrail_settings()
        paper_mode = settings["paper_trading_mode"] or not is_dhan_configured()

        trade_date = datetime.datetime.now().strftime("%Y-%m-%d")
        trade_time = datetime.datetime.now().strftime("%H:%M:%S")
        dhan_order_id: Optional[str] = None
        dhan_response: Optional[Dict[str, Any]] = None

        if not paper_mode and asset_category == "STOCK":
            security_id = await resolve_security_id(symbol)
            if not security_id:
                raise ValueError(
                    f"Could not resolve Dhan security_id for '{symbol}'."
                )

            dhan_response = await place_order_raw(
                security_id=security_id,
                exchange_segment=NSE_EQ,
                transaction_type=BUY if trade_type == "BUY" else SELL,
                quantity=quantity,
                order_type=MARKET,
                product_type=INTRADAY if product_type == "INTRADAY" else DELIVERY,
                price=0,
            )
            dhan_order_id = _extract_order_id(dhan_response)

        order_id = dhan_order_id or (
            f"DHAN_PAPER_{uuid.uuid4().hex[:10].upper()}"
        )

        total_value = round(price * quantity, 2)
        brokerage = _estimate_brokerage(total_value, product_type)

        async with AsyncSessionLocal() as session:
            trade = StockTradeLog(
                trade_date=trade_date,
                trade_time=trade_time,
                symbol=symbol,
                trade_type=trade_type,
                product_type=product_type,
                asset_category=asset_category,
                quantity=quantity,
                price=price,
                stop_loss=stop_loss,
                target_price=target_price,
                brokerage=brokerage,
                realized_pnl=0.0,
                dhan_order_id=order_id,
                status="OPEN" if product_type == "INTRADAY" else "EXECUTED",
                notes=(
                    notes
                    or f"Executed via {'DhanHQ Live' if not paper_mode else 'Paper Trading'}"
                ),
            )
            session.add(trade)
            await session.commit()
            await session.refresh(trade)

            return {
                "order_id": order_id,
                "status": "SUCCESS",
                "symbol": symbol,
                "trade_type": trade_type,
                "product_type": product_type,
                "asset_category": asset_category,
                "quantity": quantity,
                "price": price,
                "total_val": total_value,
                "mode": "DHANHQ_LIVE" if not paper_mode else "PAPER_TRADING",
                "trade_log_id": trade.id,
                "executed_at": f"{trade_date} {trade_time}",
                "dhan_raw_response": dhan_response,
            }

    except DhanAPIError as exc:
        raise ValueError(f"DhanHQ live order failed: {exc}") from exc
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Failed to place order: {exc}") from exc


def _estimate_brokerage(total_value: float, product_type: str) -> float:
    """Keep the existing application's simple brokerage estimate."""
    if product_type == "INTRADAY":
        return round(min(20.0, total_value * 0.0003), 2)
    return round(total_value * 0.001, 2)


async def square_off_position(
    trade_id: int,
    exit_price: float,
    notes: Optional[str] = None,
):
    """Close a local trade record and calculate realized P&L."""
    try:
        async with AsyncSessionLocal() as session:
            trade = await session.get(StockTradeLog, trade_id)
            if not trade:
                raise ValueError(f"Trade log ID {trade_id} not found.")

            if trade.status == "SQUARED_OFF":
                return {"message": f"Trade #{trade_id} is already squared off."}

            price_difference = (
                exit_price - trade.price
                if trade.trade_type == "BUY"
                else trade.price - exit_price
            )
            pnl = (price_difference * trade.quantity) - (trade.brokerage or 0.0)

            trade.status = "SQUARED_OFF"
            trade.realized_pnl = round(pnl, 2)
            if notes:
                trade.notes = f"{trade.notes or ''} | Exit Note: {notes}".strip()

            await session.commit()

            return {
                "trade_id": trade.id,
                "symbol": trade.symbol,
                "entry_price": trade.price,
                "exit_price": exit_price,
                "quantity": trade.quantity,
                "realized_pnl": round(pnl, 2),
                "status": "SQUARED_OFF",
            }
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Failed to square off position: {exc}") from exc


async def get_holdings():
    """Return normalized Dhan holdings and portfolio summary."""
    try:
        if not is_dhan_configured():
            return _warning(
                "DhanHQ credentials not configured. Set DHAN_CLIENT_ID and "
                "DHAN_ACCESS_TOKEN in backend/.env.",
                summary={},
                holdings=[],
            )

        raw = await get_holdings_raw()
        return _process_holdings(raw)
    except DhanAPIError as exc:
        return _warning(str(exc), summary={}, holdings=[])
    except Exception as exc:
        return _warning(f"Unexpected error while fetching Dhan holdings: {exc}", summary={}, holdings=[])


def _process_holdings(raw_data: Any) -> Dict[str, Any]:
    items = raw_data if isinstance(raw_data, list) else raw_data.get("data", []) if isinstance(raw_data, dict) else []

    holdings = []
    total_investment = 0.0
    current_value = 0.0
    total_pnl = 0.0
    day_pnl = 0.0

    for item in items:
        qty = int(item.get("totalQty") or item.get("total_qty") or item.get("quantity") or 0)
        dp_qty = int(item.get("dpQty") or item.get("dp_qty") or item.get("available_qty") or 0)
        t1_qty = int(item.get("t1Qty") or item.get("t1_qty") or 0)
        collateral_qty = int(item.get("collateralQty") or item.get("collateral_qty") or 0)
        avg_price = float(item.get("avgCostPrice") or item.get("avg_cost_price") or item.get("averagePrice") or item.get("price") or 0)
        ltp = float(item.get("lastTradedPrice") or item.get("ltp") or item.get("current_price") or avg_price)
        close_price = float(item.get("closePrice") or item.get("close_price") or ltp)

        invested = round(qty * avg_price, 2)
        current = round(qty * ltp, 2)
        pnl = round(current - invested, 2)
        day = round(qty * (ltp - close_price), 2)
        symbol = str(item.get("tradingSymbol") or item.get("trading_symbol") or item.get("symbol") or "UNKNOWN").upper()

        holdings.append({
            "symbol": symbol,
            "trading_symbol": symbol,
            "exchange": item.get("exchangeSegment") or item.get("exchange") or "NSE",
            "isin": item.get("isin") or item.get("security_id") or "—",
            "security_id": item.get("securityId") or item.get("security_id") or "",
            "total_qty": qty,
            "dp_qty": dp_qty,
            "t1_qty": t1_qty,
            "collateral_qty": collateral_qty,
            "avg_price": round(avg_price, 2),
            "ltp": round(ltp, 2),
            "close_price": round(close_price, 2),
            "invested_value": invested,
            "current_value": current,
            "pnl": pnl,
            "pnl_pct": round((pnl / invested) * 100, 2) if invested else 0.0,
            "day_pnl": day,
            "day_pnl_pct": round(((ltp - close_price) / close_price) * 100, 2) if close_price else 0.0,
        })

        total_investment += invested
        current_value += current
        total_pnl += pnl
        day_pnl += day

    previous_value = current_value - day_pnl

    return {
        "status": "success",
        "is_live": True,
        "broker": "DhanHQ",
        "endpoint": "dhanhq-sdk",
        "warning": None,
        "summary": {
            "total_investment": round(total_investment, 2),
            "current_value": round(current_value, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round((total_pnl / total_investment) * 100, 2) if total_investment else 0.0,
            "day_pnl": round(day_pnl, 2),
            "day_pnl_pct": round((day_pnl / previous_value) * 100, 2) if previous_value > 0 else 0.0,
            "total_stocks": len(holdings),
        },
        "holdings": holdings,
    }


async def get_holding_detail(symbol_or_isin: str):
    """Find one holding by symbol, ISIN, or security ID."""
    try:
        response = await get_holdings()
        target = symbol_or_isin.upper().replace(".NS", "").replace(".BO", "").strip()

        for holding in response.get("holdings", []):
            if (
                holding["symbol"].upper() == target
                or str(holding.get("isin", "")).upper() == target
                or str(holding.get("security_id", "")) == target
            ):
                return {
                    "status": "success",
                    "broker": response.get("broker", "DhanHQ"),
                    "is_live": response.get("is_live", False),
                    "warning": response.get("warning"),
                    "holding": holding,
                }

        warning = response.get("warning")
        if warning:
            raise ValueError(f"{warning} (Stock '{symbol_or_isin}' cannot be looked up.)")
        raise ValueError(f"Holding '{symbol_or_isin}' not found in Dhan account.")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Failed to fetch holding detail: {exc}") from exc


async def get_margin_snapshot():
    """Return available Dhan margin for strategy/risk checks."""
    try:
        if not is_dhan_configured():
            return {"status": "warning", "warning": "DhanHQ not configured.", "available_margin": 0.0}

        raw = await get_fund_limits_raw()
        data = raw.get("data", raw) if isinstance(raw, dict) else raw
        available = 0.0
        if isinstance(data, dict):
            available = data.get("availabelBalance", data.get("availableBalance", 0.0)) or 0.0

        return {"status": "success", "available_margin": float(available), "raw": data}
    except DhanAPIError as exc:
        return {"status": "error", "warning": str(exc), "available_margin": 0.0}
    except Exception as exc:
        return {"status": "error", "warning": str(exc), "available_margin": 0.0}


async def get_orders():
    try:
        if not is_dhan_configured():
            return {"status": "warning", "is_live": False, "warning": "DhanHQ not configured.", "orders": []}
        raw = await get_order_list_raw()
        orders = raw if isinstance(raw, list) else (raw.get("data") or []) if isinstance(raw, dict) else []
        return {"status": "success", "is_live": True, "orders": orders}
    except DhanAPIError as exc:
        return {"status": "error", "is_live": False, "warning": str(exc), "orders": []}
    except Exception as exc:
        return {"status": "error", "is_live": False, "warning": str(exc), "orders": []}


async def get_order_detail(order_id: str):
    try:
        if not is_dhan_configured():
            return {"status": "warning", "is_live": False, "warning": "DhanHQ not configured.", "order": None}
        raw = await get_order_by_id_raw(order_id)
        return {"status": "success", "is_live": True, "order": raw}
    except DhanAPIError as exc:
        return {"status": "error", "is_live": False, "warning": str(exc), "order": None}
    except Exception as exc:
        return {"status": "error", "is_live": False, "warning": str(exc), "order": None}


async def cancel_order(order_id: str):
    try:
        if not is_dhan_configured():
            raise ValueError("DhanHQ not configured — cannot cancel a live order.")
        raw = await cancel_order_raw(order_id)
        return {"status": "success", "order_id": order_id, "response": raw}
    except ValueError:
        raise
    except DhanAPIError as exc:
        raise ValueError(f"Failed to cancel order {order_id}: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Failed to cancel order {order_id}: {exc}") from exc


__all__ = [
    "place_order",
    "square_off_position",
    "get_holdings",
    "get_holding_detail",
    "get_margin_snapshot",
    "get_orders",
    "get_order_detail",
    "cancel_order",
]
