"""Account reads. Paper mode returns the local ledger. Live mode returns Dhan."""

from fastapi import APIRouter, HTTPException

from app.broker.dhan_gateway import DhanRequestError
from app.broker.paper_ledger import PaperLedgerError
from app.broker.trading_gateway import get_trading_gateway

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/funds")
async def get_funds():
    """Cash available for a new intraday reserve, in INR."""
    try:
        gateway = get_trading_gateway()
        balance = await gateway.get_available_balance_inr()
    except (DhanRequestError, PaperLedgerError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"mode": gateway.mode, "available_balance_inr": round(balance, 2)}


@router.get("/positions")
async def get_positions():
    """Open intraday positions. Quantity is signed shares: positive long, negative short."""
    try:
        gateway = get_trading_gateway()
        positions = await gateway.get_open_positions()
    except (DhanRequestError, PaperLedgerError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"mode": gateway.mode, "count": len(positions), "positions": positions}


@router.get("/orders")
async def get_orders():
    """Live orders from Dhan, or paper fills from the ledger."""
    try:
        gateway = get_trading_gateway()
        orders = await gateway.get_orders()
    except (DhanRequestError, PaperLedgerError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"mode": gateway.mode, "count": len(orders), "orders": orders}
