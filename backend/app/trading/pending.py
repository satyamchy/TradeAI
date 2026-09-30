"""Pending suggestions and delivery requests.

Nothing here reaches Dhan until `execute_pending_order`. The trader who
owns the row is the only one who can execute or reject it.
"""

from __future__ import annotations

import json

from app import db
from app.broker.trading_gateway import gateway_for_user
from app.trading.automation_runner import automation_runner
from app.trading.nifty50 import normalize_symbol
from app.trading.nse_session import is_nse_cash_session_open, is_past_entry_cutoff, is_square_off_time
from app.trading.risk_limits import check_new_entry, daily_loss_halt
from app.trading.screener import last_traded_prices
from app.trading.suggestions import build_suggestion


class PendingOrderError(Exception):
    """The pending row cannot be created or executed."""


def _own(user: dict, row: dict | None) -> dict:
    if row is None or row["user_id"] != user["id"]:
        raise PendingOrderError("Pending order not found")
    if row["status"] != "pending":
        raise PendingOrderError("That request is no longer pending")
    return row


async def create_suggestion(user: dict) -> dict:
    """Store one checked suggestion. Does not place it."""
    gateway = gateway_for_user(user)
    positions = await gateway.get_open_positions()
    intraday = [row for row in positions if row.get("product_type", "INTRADAY") == "INTRADAY"]
    balance = await gateway.get_available_balance_inr()
    try:
        sized = await build_suggestion(automation_runner.limits, balance, len(intraday))
    except ValueError as exc:
        raise PendingOrderError(str(exc)) from exc
    saved = db.add_pending(
        user["id"],
        "suggestion",
        sized["product"],
        sized["symbol"],
        sized["side"],
        sized["quantity"],
        sized["price"],
        sized["detail"],
    )
    db.add_event(
        user["id"],
        "suggestion",
        "requested",
        symbol=saved["symbol"],
        side=saved["side"],
        quantity=saved["quantity"],
        product=saved["product"],
        detail=saved["detail"],
    )
    return saved


async def create_delivery(user: dict, symbol: str, side: str, quantity: int) -> dict:
    """Store a delivery request. Does not place it."""
    symbol = normalize_symbol(symbol)
    prices = await last_traded_prices([symbol])
    price = float(prices.get(symbol) or 0)
    if price <= 0:
        raise PendingOrderError(f"No price for {symbol}")
    saved = db.add_pending(
        user["id"],
        "delivery",
        "DELIVERY",
        symbol,
        side,
        quantity,
        price,
        "Delivery request. Not an order until you execute it.",
    )
    db.add_event(
        user["id"],
        "delivery_request",
        "requested",
        symbol=symbol,
        side=side,
        quantity=quantity,
        product="DELIVERY",
    )
    return saved


async def execute_pending_order(user: dict, pending_id: int) -> dict:
    """Place the pending row, after the risk checks. Only the owner may call this."""
    if user["role"] != "trader":
        raise PendingOrderError("Only a trader can execute")
    row = _own(user, db.get_pending(pending_id))
    gateway = gateway_for_user(user)
    positions = await gateway.get_open_positions()
    intraday = [item for item in positions if item.get("product_type", "INTRADAY") == "INTRADAY"]
    balance = await gateway.get_available_balance_inr()
    realized = await gateway.realized_pnl_today_inr()
    security_id = await gateway.resolve_security_id(row["symbol"])
    reason = check_new_entry(
        symbol=row["symbol"],
        security_id=security_id,
        side=row["side"],
        quantity=int(row["quantity"]),
        price=float(row["price"]),
        balance_inr=balance,
        open_position_count=len(intraday),
        limits=automation_runner.limits,
        session_open=is_nse_cash_session_open(),
        past_entry_cutoff=is_past_entry_cutoff(),
        square_off_due=is_square_off_time(),
        daily_loss_halt=daily_loss_halt(realized, automation_runner.limits.max_daily_loss_inr),
        product_type=row["product"],
    )
    if reason:
        db.add_event(
            user["id"],
            "execute",
            "failed",
            symbol=row["symbol"],
            side=row["side"],
            quantity=row["quantity"],
            product=row["product"],
            detail=reason,
        )
        raise PendingOrderError(reason)
    placed = await gateway.place_intraday_order(
        row["symbol"],
        security_id,
        row["side"],
        int(row["quantity"]),
        float(row["price"]),
        product_type=row["product"],
    )
    db.set_pending_status(row["id"], "executed")
    db.add_event(
        user["id"],
        "execute",
        "placed",
        symbol=row["symbol"],
        side=row["side"],
        quantity=row["quantity"],
        product=row["product"],
        detail=row["source"],
    )
    return {"pending_id": row["id"], "order": placed}


def reject_pending_order(user: dict, pending_id: int) -> dict:
    """Drop a pending row. Only the owner may call this."""
    if user["role"] != "trader":
        raise PendingOrderError("Only a trader can reject")
    row = _own(user, db.get_pending(pending_id))
    db.set_pending_status(row["id"], "rejected")
    db.add_event(
        user["id"],
        "reject",
        "rejected",
        symbol=row["symbol"],
        side=row["side"],
        quantity=row["quantity"],
        product=row["product"],
        detail=row["source"],
    )
    return {"pending_id": row["id"], "status": "rejected"}


def set_user_automation(user: dict, state: str, methods: list[str]) -> None:
    """Persist entries, exits_only, or off for this trader."""
    db.set_automation(user["id"], state, json.dumps(methods))
    db.add_event(user["id"], "automation", state, detail=",".join(methods))
