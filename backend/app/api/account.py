"""This user's funds, positions, and orders. Live mode uses their Dhan token."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app import db
from app.auth import current_user, encrypt_secret, require_trader
from app.broker.dhan_gateway import DhanRequestError
from app.broker.paper_ledger import PaperLedgerError
from app.broker.trading_gateway import gateway_for_user

router = APIRouter(prefix="/account", tags=["account"])


class DhanCredentialsRequest(BaseModel):
    """Dhan client id and access token. They are encrypted before storage."""

    client_id: str = Field(min_length=1)
    access_token: str = Field(min_length=1)


@router.get("/funds")
async def get_funds(request: Request):
    """Cash available for a new reserve, in INR. 401 when logged out. 502 when Dhan fails."""
    user = current_user(request)
    try:
        balance = await gateway_for_user(user).get_available_balance_inr()
    except (DhanRequestError, PaperLedgerError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"mode": gateway_for_user(user).mode, "available_balance_inr": round(balance, 2)}


@router.get("/positions")
async def get_positions(request: Request):
    """Open positions for this user. Quantity is signed shares. 401 when logged out."""
    user = current_user(request)
    try:
        positions = await gateway_for_user(user).get_open_positions()
    except (DhanRequestError, PaperLedgerError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"mode": gateway_for_user(user).mode, "count": len(positions), "positions": positions}


@router.get("/orders")
async def get_orders(request: Request):
    """This user's live orders, or their paper fills. 401 when logged out."""
    user = current_user(request)
    try:
        orders = await gateway_for_user(user).get_orders()
    except (DhanRequestError, PaperLedgerError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"mode": gateway_for_user(user).mode, "count": len(orders), "orders": orders}


@router.put("/dhan-credentials")
def put_dhan_credentials(body: DhanCredentialsRequest, request: Request):
    """Save this trader's Dhan client id and access token.

    403 unless the caller is a trader. 400 when CREDENTIALS_KEY is missing.
    The response says only that they were saved.
    """
    user = require_trader(request)
    db.save_dhan_credentials(
        user["id"],
        encrypt_secret(body.client_id.strip()),
        encrypt_secret(body.access_token.strip()),
    )
    db.add_event(user["id"], "dhan_credentials", "placed", detail="credentials saved")
    return {"dhan_saved": True}
