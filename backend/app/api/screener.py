"""Ranked NIFTY 50 names. This route does not place orders."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from app.auth import current_user
from app.modules.stock_selection.schemas import RankCandidatesRequest
from app.modules.stock_selection.service import StockSelectionService
from app.trading.nifty50 import INDEX_CHOICES, canonical_index

router = APIRouter(prefix="/screener", tags=["screener"])


def _stock_selection_service(request: Request) -> StockSelectionService:
    service = getattr(request.app.state, "stock_selection_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Stock selection service is not available")
    return service


@router.get("/nifty50")
async def get_nifty50_ranking(
    request: Request,
    side: Literal["long", "short"],
    limit: int = Query(default=6, ge=1, le=50),
    index: str = Query(default="NIFTY 50"),
):
    """Top names for a long, or the weakest names for a short.

    `side=long` sorts by the highest score. `side=short` sorts by the lowest.
    401 when logged out. Nothing is placed.
    """
    current_user(request)
    if index.strip().upper() not in {key.upper() for key in INDEX_CHOICES}:
        raise HTTPException(status_code=400, detail="index must be one of the NSE lists")
    try:
        candidates = await _stock_selection_service(request).rank_candidates(
            RankCandidatesRequest(side=side, limit=limit, index=canonical_index(index))
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "side": side,
        "index": canonical_index(index),
        "count": len(candidates),
        "candidates": [candidate.model_dump(exclude_none=True) for candidate in candidates],
    }
