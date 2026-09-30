"""Ask for one suggestion. The reply is stored. It is not sent to Dhan."""

from fastapi import APIRouter, HTTPException, Request

from app.auth import require_trader
from app.trading.pending import PendingOrderError, create_suggestion

router = APIRouter(prefix="/suggestions", tags=["suggestions"])


@router.post("")
async def post_suggestion(request: Request):
    """Build one pending suggestion from the screener list.

    403 for viewers and admins. 400 when the model reply is not one of the
    offered names, or when no cash is left. Nothing is placed.
    """
    user = require_trader(request)
    try:
        return await create_suggestion(user)
    except PendingOrderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
