"""Ranked NIFTY 50 names. This route does not place orders."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.trading.screener import rank_nifty50

router = APIRouter(prefix="/screener", tags=["screener"])


@router.get("/nifty50")
async def get_nifty50_ranking(
    side: Literal["long", "short"],
    limit: int = Query(default=6, ge=1, le=50),
):
    """Top names for a long, or the weakest names for a short.

    `side=long` sorts by the highest score. `side=short` sorts by the lowest.
    `limit` is how many symbols to return.
    """
    try:
        candidates = await rank_nifty50(side, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"side": side, "count": len(candidates), "candidates": candidates}
