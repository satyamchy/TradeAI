"""Orders a person asked for.

An intraday order the trader typed is placed on this request. A delivery
request and an LLM suggestion wait in the pending list until Execute.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app import db
from app.auth import current_user, require_trader
from app.broker.dhan_gateway import DhanRequestError
from app.broker.paper_ledger import PaperLedgerError
from app.broker.trading_gateway import gateway_for_user
from app.trading.automation_runner import automation_runner
from app.trading.nifty50 import normalize_symbol
from app.trading.nse_session import is_nse_cash_session_open, is_past_entry_cutoff, is_square_off_time
from app.trading.pending import PendingOrderError, create_delivery, execute_pending_order, reject_pending_order
from app.trading.risk_limits import check_new_entry, daily_loss_halt
from app.trading.screener import last_traded_prices

router = APIRouter(prefix="/orders", tags=["orders"])


class IntradayOrderRequest(BaseModel):
    """A single NSE intraday market order. Quantity is a positive share count."""

    symbol: str = Field(min_length=1)
    side: str = Field(pattern="^(BUY|SELL)$")
    quantity: int = Field(gt=0)


class DeliveryOrderRequest(BaseModel):
    """A delivery request. It is not sent to Dhan until Execute."""

    symbol: str = Field(min_length=1)
    side: str = Field(pattern="^(BUY|SELL)$")
    quantity: int = Field(gt=0)


@router.post("/intraday")
async def place_manual_intraday_order(body: IntradayOrderRequest, request: Request):
    """Place one intraday market order for this trader.

    403 unless the caller is a trader. 400 when the session is closed or a
    risk check fails. This click is the person, so it does not wait in the queue.
    """
    user = require_trader(request)
    if not is_nse_cash_session_open():
        raise HTTPException(status_code=400, detail="NSE cash session is closed")

    gateway = gateway_for_user(user)
    symbol = normalize_symbol(body.symbol)
    try:
        positions = await gateway.get_open_positions()
        prices = await last_traded_prices([symbol])
    except DhanRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    intraday = [row for row in positions if row.get("product_type", "INTRADAY") == "INTRADAY"]
    current = next((row for row in intraday if row["symbol"] == symbol), None)
    price = prices.get(symbol) or (float(current["last_price"]) if current else 0)
    if price <= 0:
        raise HTTPException(status_code=400, detail=f"No price for {symbol}")

    closing = _closing_quantity(current, body.side, body.quantity)
    security_id = (current or {}).get("security_id") or await gateway.resolve_security_id(symbol)
    if closing is None:
        balance = await gateway.get_available_balance_inr()
        realized = await gateway.realized_pnl_today_inr()
        reason = check_new_entry(
            symbol=symbol,
            security_id=security_id,
            side=body.side,
            quantity=body.quantity,
            price=price,
            balance_inr=balance,
            open_position_count=len(intraday),
            limits=automation_runner.limits,
            session_open=True,
            past_entry_cutoff=is_past_entry_cutoff(),
            square_off_due=is_square_off_time(),
            daily_loss_halt=daily_loss_halt(realized, automation_runner.limits.max_daily_loss_inr),
        )
        if reason:
            db.add_event(user["id"], "intraday_order", "failed", symbol=symbol, side=body.side, quantity=body.quantity, product="INTRADAY", detail=reason)
            raise HTTPException(status_code=400, detail=reason)
    elif not security_id:
        raise HTTPException(status_code=400, detail="Dhan security id is missing")

    try:
        placed = await gateway.place_intraday_order(symbol, security_id, body.side, body.quantity, price)
    except (PaperLedgerError, DhanRequestError, ValueError) as exc:
        db.add_event(user["id"], "intraday_order", "failed", symbol=symbol, side=body.side, quantity=body.quantity, product="INTRADAY", detail=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.add_event(user["id"], "intraday_order", "placed", symbol=symbol, side=body.side, quantity=body.quantity, product="INTRADAY")
    return placed


@router.post("/delivery")
async def post_delivery(body: DeliveryOrderRequest, request: Request):
    """Save a delivery request. 403 for non-traders. 400 when there is no price. Nothing is placed."""
    user = require_trader(request)
    try:
        return await create_delivery(user, body.symbol, body.side, body.quantity)
    except PendingOrderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/pending")
def get_pending(request: Request):
    """This user's suggestions and delivery requests that are still waiting. 401 when logged out."""
    user = current_user(request)
    rows = db.list_pending(user["id"])
    return {"count": len(rows), "orders": rows}


@router.post("/pending/{pending_id}/execute")
async def post_execute(pending_id: int, request: Request):
    """Place one pending suggestion or delivery order.

    403 unless the caller is the trader who owns it. 400 when a risk check
    fails. This is the only route that sends a pending row to Dhan.
    """
    user = require_trader(request)
    try:
        return await execute_pending_order(user, pending_id)
    except PendingOrderError as exc:
        status = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except (DhanRequestError, PaperLedgerError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/pending/{pending_id}/reject")
def post_reject(pending_id: int, request: Request):
    """Drop a pending row. 403 unless the caller is the trader who owns it."""
    user = require_trader(request)
    try:
        return reject_pending_order(user, pending_id)
    except PendingOrderError as exc:
        status = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.delete("/{dhan_order_id}")
async def cancel_intraday_order(dhan_order_id: str, request: Request):
    """Cancel a working order for this trader. 403 for non-traders. Paper market fills stay rejected."""
    user = require_trader(request)
    try:
        result = await gateway_for_user(user).cancel_order(dhan_order_id)
    except DhanRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    db.add_event(user["id"], "cancel", "placed", detail=dhan_order_id)
    return result


def _closing_quantity(position: dict | None, side: str, quantity: int) -> int | None:
    """Share count being closed, or None when this order opens or adds risk.

    A sell larger than the long, or a buy larger than the short, is rejected
    here so one request cannot flip the position.
    """
    if position is None:
        return None
    held = int(position["quantity"])
    if held > 0 and side == "SELL":
        if quantity > held:
            raise HTTPException(status_code=400, detail="quantity is larger than the long and would open a short")
        return quantity
    if held < 0 and side == "BUY":
        if quantity > abs(held):
            raise HTTPException(status_code=400, detail="quantity is larger than the short and would open a long")
        return quantity
    return None
