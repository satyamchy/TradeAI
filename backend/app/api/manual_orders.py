"""Orders a person asked for.

An intraday order the trader typed is placed on this request. A delivery
request and an LLM suggestion wait in the pending list until Execute.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app import db
from app.auth import current_user, require_trader
from app.broker.dhan_gateway import CredentialsRequired, DhanRequestError
from app.broker.paper_ledger import PaperLedgerError
from app.broker.trading_gateway import gateway_for_user
from app.trading.automation_runner import automation_runner
from app.trading.nifty50 import normalize_symbol
from app.trading.nse_session import is_nse_cash_session_open, is_past_entry_cutoff, is_square_off_time
from app.trading.pending import PendingOrderError, _universe, create_delivery, execute_pending_order, reject_pending_order
from app.trading.risk_limits import check_new_entry, daily_loss_halt, unrealized_pnl_percent
from app.trading.screener import last_traded_prices

router = APIRouter(prefix="/orders", tags=["orders"])


class IntradayOrderRequest(BaseModel):
    """A single NSE intraday market order. Quantity is a positive share count."""

    symbol: str = Field(min_length=1)
    side: str = Field(pattern="^(BUY|SELL)$")
    quantity: int = Field(gt=0)


class ClosePositionRequest(BaseModel):
    """Close one open row. The product decides which book is sold."""

    symbol: str = Field(min_length=1)
    product_type: str = Field(pattern="^(INTRADAY|DELIVERY)$")


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
    async with gateway.exclusive():
        return await _place_intraday(user, gateway, symbol, body.side, body.quantity)


async def _place_intraday(user: dict, gateway, symbol: str, side: str, quantity: int):
    try:
        positions = await gateway.get_open_positions()
        prices = await _prices(gateway, [symbol])
    except CredentialsRequired as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DhanRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    intraday = [row for row in positions if row.get("product_type", "INTRADAY") == "INTRADAY"]
    current = next((row for row in intraday if row["symbol"] == symbol), None)
    price = prices.get(symbol) or (float(current["last_price"]) if current and float(current["last_price"]) > 0 else 0)
    if price <= 0:
        raise HTTPException(status_code=400, detail=f"No price for {symbol}")

    closing = _closing_quantity(current, side, quantity)
    security_id = (current or {}).get("security_id") or await gateway.resolve_security_id(symbol)
    if closing is None:
        balance = await gateway.get_available_balance_inr()
        realized = await gateway.realized_pnl_today_inr()
        unrealized = 0.0
        for row in positions:
            qty = int(row["quantity"])
            if qty == 0:
                continue
            unrealized += unrealized_pnl_percent(float(row["average_price"]), float(row["last_price"]), qty) / 100 * float(row["average_price"]) * abs(qty)
        try:
            universe = await _universe(user)
        except PendingOrderError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        reason = check_new_entry(
            symbol=symbol,
            security_id=security_id,
            side=side,
            quantity=quantity,
            price=price,
            balance_inr=balance,
            open_position_count=len(intraday),
            limits=automation_runner.limits,
            session_open=True,
            past_entry_cutoff=is_past_entry_cutoff(),
            square_off_due=is_square_off_time(),
            daily_loss_halt=daily_loss_halt(realized, automation_runner.limits.max_daily_loss_inr, unrealized),
            allowed_symbols=universe,
        )
        if reason:
            db.add_event(user["id"], "intraday_order", "failed", symbol=symbol, side=side, quantity=quantity, product="INTRADAY", detail=reason)
            raise HTTPException(status_code=400, detail=reason)
    elif not security_id:
        raise HTTPException(status_code=400, detail="Dhan security id is missing")

    try:
        placed = await gateway.place_intraday_order(symbol, security_id, side, quantity, price)
    except (PaperLedgerError, DhanRequestError, ValueError) as exc:
        db.add_event(user["id"], "intraday_order", "failed", symbol=symbol, side=side, quantity=quantity, product="INTRADAY", detail=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.add_event(user["id"], "intraday_order", "placed", symbol=symbol, side=side, quantity=quantity, product="INTRADAY")
    return placed


@router.post("/close")
async def close_position(body: ClosePositionRequest, request: Request):
    """Sell or cover one open product row. A delivery sell with no shares is rejected."""
    user = require_trader(request)
    gateway = gateway_for_user(user)
    symbol = normalize_symbol(body.symbol)
    async with gateway.exclusive():
        if not is_nse_cash_session_open():
            raise HTTPException(status_code=400, detail="NSE cash session is closed")
        try:
            positions = await gateway.get_open_positions()
        except CredentialsRequired as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except DhanRequestError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        current = next(
            (
                row
                for row in positions
                if row["symbol"] == symbol and (row.get("product_type") or "INTRADAY") == body.product_type
            ),
            None,
        )
        if current is None or int(current["quantity"]) == 0:
            raise HTTPException(status_code=400, detail="No open position in that product")
        held = int(current["quantity"])
        if body.product_type == "DELIVERY" and held <= 0:
            raise HTTPException(status_code=400, detail="delivery sell needs shares you already hold")
        side = "SELL" if held > 0 else "BUY"
        quantity = abs(held)
        prices = await _prices(gateway, [symbol])
        price = float(prices.get(symbol) or current.get("last_price") or 0)
        if price <= 0:
            raise HTTPException(status_code=400, detail=f"No price for {symbol}")
        security_id = current.get("security_id") or await gateway.resolve_security_id(symbol)
        if not security_id:
            raise HTTPException(status_code=400, detail="Dhan security id is missing")
        try:
            await gateway.cancel_protective_stops(symbol, body.product_type)
            placed = await gateway.place_intraday_order(symbol, security_id, side, quantity, price, body.product_type)
        except CredentialsRequired as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (PaperLedgerError, DhanRequestError, ValueError) as exc:
            db.add_event(user["id"], "close", "failed", symbol=symbol, side=side, quantity=quantity, product=body.product_type, detail=str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        db.add_event(user["id"], "close", "placed", symbol=symbol, side=side, quantity=quantity, product=body.product_type)
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


async def _prices(gateway, symbols: list[str]) -> dict[str, float]:
    quote = getattr(gateway, "quote_prices", None)
    if quote is not None:
        try:
            quoted = await quote(symbols)
        except (DhanRequestError, CredentialsRequired):
            quoted = {}
        if quoted:
            return quoted
    return await last_traded_prices(symbols)


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
