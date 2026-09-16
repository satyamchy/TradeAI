"""
Trade Recommendation API Router.

Endpoints:
- POST /recommendation/analyze: Runs the full stock -> data -> Dhan account
  context -> agent -> precondition/risk checks -> BUY/DO_NOT_BUY flow.
  Read-only: never places an order. To act on a recommendation, submit it
  separately via POST /trading/orders (its own guardrail check applies there
  regardless of what recommended it).
"""

from fastapi import APIRouter, HTTPException

from app.schemas.recommendation import TradeRecommendationRequest, TradeRecommendationResponse
from app.controllers.trade_recommendation_controller import get_trade_recommendation

router = APIRouter(prefix="/recommendation", tags=["recommendation"])


@router.post("/analyze", response_model=TradeRecommendationResponse)
async def analyze_trade_recommendation(req: TradeRecommendationRequest):
    """
    Runs the recommendation flow for one ticker.

    - **Purpose**: Decision support only — combines technical analysis with
      Dhan account context (available margin, existing position) to answer
      BUY or DO_NOT_BUY, with reasoning. Does not execute anything.
    - **Method**: POST
    - **Payload**: `TradeRecommendationRequest`
    """
    try:
        result = await get_trade_recommendation(
            ticker=req.ticker,
            quantity=req.quantity or 1,
            product_type=req.product_type,
        )
        return TradeRecommendationResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate trade recommendation: {exc}")
