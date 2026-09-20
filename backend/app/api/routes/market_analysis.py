from fastapi import APIRouter, HTTPException

from app.schemas.finance.analysis import AnalyzeRequest, AnalyzeResponse, StockQuote
from app.services.llm_ticker_resolver import resolve_ticker_via_llm, TickerResolutionError
from app.services.llm_stock_analysis import analyze_stock_data

from app.schemas.finance.recommendation import RecommendRequest, RecommendResponse, TradeRecommendation, ExecutionResult
from app.services.llm_trade_recommender import generate_trade_recommendation, RecommendationError
from app.services.order_execution_service import execute_recommendation

router = APIRouter(prefix="/market/data", tags=["market-analysis"])


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    try:
        ticker, market_data = await resolve_ticker_via_llm(req.query)
    except TickerResolutionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        analysis_text = await analyze_stock_data(ticker, market_data)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Analysis generation failed: {exc}") from exc

    quote_data = market_data["quote"]
    return AnalyzeResponse(
        query=req.query,
        resolved_ticker=ticker,
        resolution_confidence="llm_resolved",
        quote=StockQuote(**{
            "symbol": quote_data["symbol"],
            "name": quote_data["name"],
            "current_price": quote_data["current_price"],
            "previous_close": quote_data["previous_close"],
            "day_high": quote_data["day_high"],
            "day_low": quote_data["day_low"],
            "volume": quote_data["volume"],
            "currency": quote_data["currency"],
        }),
        analysis=analysis_text,
        stock_history=market_data,
    )





@router.post("/recommend", response_model=RecommendResponse)
async def recommend(req: RecommendRequest):
    try:
        ticker, market_data = await resolve_ticker_via_llm(req.query)
    except TickerResolutionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        rec = await generate_trade_recommendation(ticker, market_data)
    except RecommendationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    execution = {"attempted": False, "executed": False, "reason": "execute=false, recommendation only", "order_id": None}
    if req.execute:
        # NOTE: security_id/exchange here are placeholders — this endpoint currently has
        # no link to the Dhan security master, so live execution is not wired up yet.
        # Fill in once /market/resolve (security-master-backed) is in place.
    #     execution = await execute_recommendation(
    #     instrument_security_id=resolved.security_id,
    #     exchange=resolved.exchange,
    #     recommendation=rec,
    #     quantity=req.quantity,
    # )
        execution = {"attempted": True, "executed": False, "reason": "No security_id resolution available yet — execution disabled", "order_id": None}

    return RecommendResponse(
        query=req.query,
        resolved_ticker=ticker,
        quote=market_data["quote"],
        recommendation=TradeRecommendation(**rec),
        execution=ExecutionResult(**execution),
    )