"""One-off intraday orders from the operator.

New exposure uses the same entry checks as the loop, except the loop does
not have to be enabled. Closing shares already held is allowed after the
14:45 entry cutoff. Flattening outside the session is the square-off route.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.broker.dhan_gateway import DhanRequestError
from app.broker.paper_ledger import PaperLedgerError
from app.broker.trading_gateway import get_trading_gateway
from app.trading.automation_runner import automation_runner
from app.trading.nifty50 import normalize_symbol
from app.trading.nse_session import is_nse_cash_session_open, is_past_entry_cutoff, is_square_off_time
from app.trading.risk_limits import check_new_entry, daily_loss_halt
from app.trading.screener import last_traded_prices

router = APIRouter(prefix="/orders", tags=["orders"])


class IntradayOrderRequest(BaseModel):
    """A single NSE intraday market order. Quantity is a positive share count."""

    symbol: str = Field(min_length=1)
    side: str = Field(pattern="^(BUY|SELL)$")
    quantity: int = Field(gt=0)


@router.post("/intraday")
async def place_manual_intraday_order(body: IntradayOrderRequest):
    """Place one intraday market order in the current mode, paper or live."""
    if not is_nse_cash_session_open():
        raise HTTPException(status_code=400, detail="NSE cash session is closed")

    gateway = get_trading_gateway()
    symbol = normalize_symbol(body.symbol)
    try:
        positions = await gateway.get_open_positions()
        prices = await last_traded_prices([symbol])
    except DhanRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    current = next((row for row in positions if row["symbol"] == symbol), None)
    price = prices.get(symbol) or (float(current["last_price"]) if current else 0)
    if price <= 0:
        raise HTTPException(status_code=400, detail=f"No price for {symbol}")

    closing = _closing_quantity(current, body.side, body.quantity)
    security_id = None
    if current and current.get("security_id"):
        security_id = current["security_id"]
    if not security_id:
        security_id = await gateway.resolve_security_id(symbol)

    if closing is None:
        realized = await gateway.realized_pnl_today_inr()
        balance = await gateway.get_available_balance_inr()
        reason = check_new_entry(
            symbol=symbol,
            security_id=security_id,
            side=body.side,
            quantity=body.quantity,
            price=price,
            balance_inr=balance,
            open_position_count=len(positions),
            limits=automation_runner.limits,
            session_open=True,
            past_entry_cutoff=is_past_entry_cutoff(),
            square_off_due=is_square_off_time(),
            daily_loss_halt=daily_loss_halt(realized, automation_runner.limits.max_daily_loss_inr),
        )
        if reason:
            raise HTTPException(status_code=400, detail=reason)
    elif not security_id:
        raise HTTPException(status_code=400, detail="Dhan security id is missing")

    try:
        return await gateway.place_intraday_order(symbol, security_id, body.side, body.quantity, price)
    except (PaperLedgerError, DhanRequestError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{dhan_order_id}")
async def cancel_intraday_order(dhan_order_id: str):
    """Cancel a working order. Paper market fills are already done and stay rejected."""
    try:
        return await get_trading_gateway().cancel_order(dhan_order_id)
    except DhanRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _closing_quantity(position: dict | None, side: str, quantity: int) -> int | None:
    """Share count being closed, or None when this order opens or adds risk.

    A sell larger than the long, or a buy larger than the short, is rejected
    here. That order would flip the position, and the ledger will not do that
    in one fill.
    """
    if position is None:
        return None
    held = int(position["quantity"])
    if held > 0 and side == "SELL":
        if quantity > held:
            raise HTTPException(
                status_code=400,
                detail="quantity is larger than the long and would open a short",
            )
        return quantity
    if held < 0 and side == "BUY":
        if quantity > abs(held):
            raise HTTPException(
                status_code=400,
                detail="quantity is larger than the short and would open a long",
            )
        return quantity
    return None
