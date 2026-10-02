"""Pending suggestions and delivery requests.

Nothing here reaches Dhan until `execute_pending_order`. The trader who
owns the row is the only one who can execute or reject it.
"""

from __future__ import annotations

import json
import uuid

from app import db
from app.broker.dhan_gateway import DhanRequestError
from app.broker.paper_ledger import PaperLedgerError
from app.broker.trading_gateway import gateway_for_user
from app.trading.automation_runner import automation_runner
from app.trading.nifty50 import canonical_index, normalize_symbol
from app.trading.nse_session import is_nse_cash_session_open, is_past_entry_cutoff, is_square_off_time
from app.trading.risk_limits import check_new_entry, daily_loss_halt
from app.trading.screener import allowed_symbols, last_traded_prices
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
        sized = await build_suggestion(
            automation_runner.limits,
            balance,
            len(intraday),
            index=user.get("trading_index"),
        )
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
    """Place the pending row. Only one caller can claim it, and the price is read again."""
    if user["role"] != "trader":
        raise PendingOrderError("Only a trader can execute")
    correlation = "tx" + uuid.uuid4().hex[:18]
    row = db.claim_pending(pending_id, user["id"], correlation)
    if row is None:
        _own(user, db.get_pending(pending_id))
        raise PendingOrderError("That request is no longer pending")
    gateway = gateway_for_user(user)
    async with gateway.exclusive():
        return await _execute_claimed(user, gateway, row, correlation)


async def _execute_claimed(user: dict, gateway, row: dict, correlation: str) -> dict:
    try:
        return await _send_claimed(user, gateway, row, correlation)
    except PendingOrderError:
        current = db.get_pending(row["id"])
        if current and current["status"] == "executing":
            db.set_pending_status(row["id"], "pending")
        raise


async def _send_claimed(user: dict, gateway, row: dict, correlation: str) -> dict:
    if not is_nse_cash_session_open():
        raise PendingOrderError("NSE cash session is closed")
    prices = await _fresh_prices(gateway, [row["symbol"]])
    price = float(prices.get(normalize_symbol(row["symbol"])) or 0)
    if price <= 0:
        raise PendingOrderError(f"No price for {row['symbol']}")

    positions = await gateway.get_open_positions()
    product = row["product"]
    current = _match(positions, row["symbol"], product)
    intraday = [item for item in positions if item.get("product_type", "INTRADAY") == "INTRADAY"]
    reducing = _reducing(current, row["side"], int(row["quantity"]))
    if product == "DELIVERY" and row["side"] == "SELL" and reducing is None:
        raise PendingOrderError("delivery sell needs shares you already hold")

    security_id = (current or {}).get("security_id") or await gateway.resolve_security_id(row["symbol"])
    if reducing is None:
        balance = await gateway.get_available_balance_inr()
        realized = await gateway.realized_pnl_today_inr()
        unrealized = _unrealized(positions)
        universe = await _universe(user)
        reason = check_new_entry(
            symbol=row["symbol"],
            security_id=security_id,
            side=row["side"],
            quantity=int(row["quantity"]),
            price=price,
            balance_inr=balance,
            open_position_count=len(intraday),
            limits=automation_runner.limits,
            session_open=True,
            past_entry_cutoff=is_past_entry_cutoff(),
            square_off_due=is_square_off_time(),
            daily_loss_halt=daily_loss_halt(realized, automation_runner.limits.max_daily_loss_inr, unrealized),
            product_type=product,
            allowed_symbols=universe,
        )
        if reason:
            db.add_event(
                user["id"], "execute", "failed",
                symbol=row["symbol"], side=row["side"], quantity=row["quantity"],
                product=product, detail=reason,
            )
            raise PendingOrderError(reason)
    elif not security_id:
        raise PendingOrderError("Dhan security id is missing")

    try:
        placed = await gateway.place_tagged_order(
            row["symbol"], security_id, row["side"], int(row["quantity"]), price, product, correlation
        )
    except (PaperLedgerError, DhanRequestError, ValueError) as exc:
        db.set_pending_status(row["id"], "failed")
        db.add_event(
            user["id"], "execute", "failed",
            symbol=row["symbol"], side=row["side"], quantity=row["quantity"],
            product=product, detail=str(exc),
        )
        raise PendingOrderError(str(exc)) from exc

    order_id = str(placed.get("order_id") or "")
    if order_id:
        db.set_pending_broker(row["id"], order_id)
    status = str(placed.get("status") or "").upper()
    if status in {"REJECTED", "CANCELLED", "EXPIRED", "FAILED"}:
        db.set_pending_status(row["id"], "failed")
        raise PendingOrderError(f"Order {status or 'failed'}")
    if status in {"UNKNOWN", "PENDING", "TRANSIT", "OPEN"}:
        db.add_event(
            user["id"], "execute", "executing",
            symbol=row["symbol"], side=row["side"], quantity=row["quantity"],
            product=product, detail=correlation,
        )
        return {"pending_id": row["id"], "status": "executing", "order": placed}
    if status in {"TRADED", "FILLED", "PART_TRADED", "PLACED"} and row["side"] in {"BUY", "SELL"} and status != "PLACED":
        arm = getattr(gateway, "arm_protective_stop", None)
        if arm and status in {"TRADED", "FILLED"}:
            try:
                await arm(
                    row["symbol"], security_id, row["side"], int(row["quantity"]), price, product,
                    automation_runner.limits.stop_loss_pct,
                )
            except (DhanRequestError, PaperLedgerError, ValueError):
                pass
    db.set_pending_status(row["id"], "executed")
    db.add_event(
        user["id"], "execute", "placed",
        symbol=row["symbol"], side=row["side"], quantity=row["quantity"],
        product=product, detail=row["source"],
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


def _match(positions: list[dict], symbol: str, product: str) -> dict | None:
    wanted = normalize_symbol(symbol)
    return next(
        (
            row
            for row in positions
            if normalize_symbol(row["symbol"]) == wanted and (row.get("product_type") or "INTRADAY") == product
        ),
        None,
    )


def _reducing(position: dict | None, side: str, quantity: int) -> int | None:
    """Share count being closed, or None when this order opens or adds risk."""
    if position is None:
        return None
    held = int(position["quantity"])
    if held > 0 and side == "SELL":
        if quantity > held:
            raise PendingOrderError("quantity is larger than the long and would open a short")
        return quantity
    if held < 0 and side == "BUY":
        if quantity > abs(held):
            raise PendingOrderError("quantity is larger than the short and would open a long")
        return quantity
    return None


def _unrealized(positions: list[dict]) -> float:
    total = 0.0
    for position in positions:
        quantity = int(position["quantity"])
        average = float(position["average_price"])
        last = float(position.get("last_price") or average)
        if quantity > 0:
            total += (last - average) * quantity
        elif quantity < 0:
            total += (average - last) * abs(quantity)
    return total


async def _universe(user: dict) -> set[str] | None:
    index = canonical_index(user.get("trading_index"))
    if index == "NIFTY 50":
        return None
    names = await allowed_symbols(index)
    if not names:
        raise PendingOrderError("selected index could not be loaded")
    return names


async def _fresh_prices(gateway, symbols: list[str]) -> dict[str, float]:
    quote = getattr(gateway, "quote_prices", None)
    if quote is not None:
        try:
            quoted = await quote(symbols)
        except (DhanRequestError, PaperLedgerError, ValueError):
            quoted = {}
        if quoted:
            return quoted
    return await last_traded_prices(symbols)


def set_user_automation(user: dict, state: str, methods: list[str]) -> None:
    """Persist entries, exits_only, or off for this trader."""
    db.set_automation(user["id"], state, json.dumps(methods))
    db.add_event(user["id"], "automation", state, detail=",".join(methods))
