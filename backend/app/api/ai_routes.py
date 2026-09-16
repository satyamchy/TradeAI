"""AI analysis and AI-assisted trading APIs."""

from fastapi import APIRouter, HTTPException

from app.schemas.trading import AIAnalysisRequest, AIConfirmRequest, AITradeRequest
from app.services.ai_analysis_service import generate_ai_stock_analysis
from app.services.market_data_service import fetch_stock_market_data
from app.services.company_resolver import resolve_ticker_symbol
from app.services.technical_analysis_service import run_technical_analysis
from app.services.trading_service import confirm_ai_order, create_pending_ai_order

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/analyze")
async def analyze(request: AIAnalysisRequest):
    try:
        ticker = resolve_ticker_symbol(request.symbol)
        market_data = await fetch_stock_market_data(ticker)
        technical = run_technical_analysis(market_data, request.analysis_type)
        ai = await generate_ai_stock_analysis(
            symbol=ticker,
            analysis_type=request.analysis_type,
            market_data=market_data,
            technical_analysis=technical,
        )
        return {
            "symbol": ticker,
            "analysis_type": request.analysis_type,
            "market": market_data.get("quote", {}),
            "technical": technical,
            "analysis": ai,
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/trade")
async def ai_trade(request: AITradeRequest):
    try:
        ticker = resolve_ticker_symbol(request.symbol)
        market_data = await fetch_stock_market_data(ticker)
        technical = run_technical_analysis(market_data, request.product_type.lower())
        ai = await generate_ai_stock_analysis(
            symbol=ticker,
            analysis_type=request.product_type.lower(),
            market_data=market_data,
            technical_analysis=technical,
        )

        side = request.side or ("BUY" if ai["recommendation"] == "BUY" else None)
        if not side:
            return {
                "status": "NO_TRADE",
                "symbol": ticker,
                "analysis": ai,
                "message": "AI returned HOLD, so no order was created.",
            }

        price = float(market_data.get("quote", {}).get("current_price") or 0)
        pending = await create_pending_ai_order(
            symbol=ticker,
            side=side,
            quantity=request.quantity,
            product_type=request.product_type,
            order_type="MARKET",
            price=price,
            notes=request.prompt or ai.get("summary"),
        )
        return {
            "status": "CONFIRMATION_REQUIRED",
            "analysis": ai,
            **pending,
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/confirm")
async def confirm(request: AIConfirmRequest):
    try:
        return await confirm_ai_order(request.order_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
