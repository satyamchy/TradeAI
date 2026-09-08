"""
Stock Analysis API Router for Phase 1.
Implements:
- POST /api/v1/stocks/analyze
Supports:
- mode: "selected" (single, multiple, or natural language name) | "top_movers"
- analysis_type: "intraday" | "delivery"
- date: YYYY-MM-DD
- top_n: integer for top_movers

Logs every analysis response for each stock to the database.
"""

import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.company_resolver import resolve_ticker_symbol
from app.services.market_data_service import fetch_stock_market_data, fetch_top_intraday_movers
from app.services.technical_analysis_service import run_technical_analysis
from app.services.ai_analysis_service import generate_ai_stock_analysis
from app.database import AsyncSessionLocal
from app.models.stock_models import StockAnalysisSnapshot

router = APIRouter(prefix="/stocks", tags=["stocks"])


class StockAnalyzeRequest(BaseModel):
    mode: str = Field(default="selected", description="selected | top_movers")
    symbols: Optional[List[str]] = Field(default=None, description="List of tickers or stock names, e.g. ['TCS.NS', 'Analyze Reliance']")
    analysis_type: str = Field(default="intraday", description="intraday | delivery")
    date: Optional[str] = Field(default=None, description="YYYY-MM-DD date string")
    top_n: Optional[int] = Field(default=5, description="Number of top movers to return if mode='top_movers'")


class SingleStockAnalysisResponse(BaseModel):
    symbol: str
    analysis_type: str
    market_data: Dict[str, Any]
    technical_analysis: Dict[str, Any]
    recommendation: str
    confidence: float
    risk_level: str
    summary: str
    key_signals: List[str]
    risks: List[str]
    selling_point: str
    disclaimer: str = "AI-generated financial decision support only. Not financial or investment advice."


async def _log_analysis_to_db(result: Dict[str, Any], date_str: str) -> Optional[int]:
    """Logs individual stock analysis response into SQLite/Postgres DB."""
    try:
        sym = result.get("symbol", "UNKNOWN")
        quote = result.get("market_data", {}).get("quote", {})
        sr = result.get("technical_analysis", {}).get("support_resistance", {})
        
        init_price = float(quote.get("current_price") or 0.0)
        target_p = float(sr.get("r1")) if sr.get("r1") else (init_price * 1.03 if init_price else None)
        stop_l = float(sr.get("s1")) if sr.get("s1") else (init_price * 0.98 if init_price else None)

        async with AsyncSessionLocal() as session:
            snapshot = StockAnalysisSnapshot(
                ticker=sym,
                symbol=sym.replace(".NS", "").replace(".BO", ""),
                name=quote.get("name", sym),
                analysis_date=date_str,
                initial_price=init_price,
                target_price=target_p,
                stop_loss=stop_l,
                currency=quote.get("currency", "INR"),
                overall_sentiment="Bullish" if result.get("recommendation") == "BUY" else ("Bearish" if result.get("recommendation") == "AVOID" else "Neutral"),
                intraday_bias="Bullish" if result.get("recommendation") == "BUY" else ("Bearish" if result.get("recommendation") == "AVOID" else "Neutral"),
                recommendation=result.get("recommendation", "HOLD"),
                technical_score=round(float(result.get("confidence", 0.7)) * 100.0, 1),
                macro_score=75.0,
                ai_reasoning=result.get("summary"),
                structured_json=result,
            )
            session.add(snapshot)
            await session.commit()
            await session.refresh(snapshot)
            return snapshot.id
    except Exception:
        return None


@router.post("/analyze", response_model=List[SingleStockAnalysisResponse])
async def analyze_stocks(req: StockAnalyzeRequest):
    """
    Main Phase 1 Stock Market Analysis Endpoint.
    Handles 'selected' stocks or 'top_movers'.
    Returns structured market data, technical indicators, and AI recommendations.
    Logs every analyzed stock to the database.
    """
    mode = req.mode.lower().strip()
    analysis_type = req.analysis_type.lower().strip()
    if analysis_type not in ["intraday", "delivery"]:
        analysis_type = "intraday"

    cur_date = req.date or datetime.datetime.now().strftime("%Y-%m-%d")
    tickers_to_analyze: List[str] = []

    if mode == "top_movers":
        top_n = req.top_n or 5
        movers = await fetch_top_intraday_movers(date_str=cur_date, top_n=top_n)
        tickers_to_analyze = [m["symbol"] for m in movers]
        if not tickers_to_analyze:
            tickers_to_analyze = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "SBIN.NS"][:top_n]
    else:
        # mode == "selected"
        raw_symbols = req.symbols or []
        if not raw_symbols:
            raise HTTPException(
                status_code=400,
                detail="At least one symbol or company name must be provided when mode='selected'.",
            )
        for s in raw_symbols:
            resolved = resolve_ticker_symbol(s)
            if resolved not in tickers_to_analyze:
                tickers_to_analyze.append(resolved)

    results: List[SingleStockAnalysisResponse] = []

    for ticker in tickers_to_analyze:
        try:
            # 1. Fetch raw market data from isolated service
            market_data = await fetch_stock_market_data(ticker)

            # 2. Compute deterministic technical indicators
            tech_analysis = run_technical_analysis(market_data, analysis_type=analysis_type)

            # 3. Generate grounded AI interpretation
            ai_eval = await generate_ai_stock_analysis(
                symbol=ticker,
                analysis_type=analysis_type,
                market_data=market_data,
                technical_analysis=tech_analysis,
            )

            stock_result = {
                "symbol": ticker,
                "analysis_type": analysis_type,
                "market_data": {
                    "quote": market_data.get("quote"),
                    "fundamentals": market_data.get("fundamentals") if analysis_type == "delivery" else {},
                    "history_summary": {
                        "total_candles": len(market_data.get("history", [])),
                        "latest_date": market_data.get("history", [{}])[-1].get("date") if market_data.get("history") else None,
                    },
                },
                "technical_analysis": tech_analysis,
                "recommendation": ai_eval.get("recommendation", "HOLD"),
                "confidence": ai_eval.get("confidence", 0.70),
                "risk_level": ai_eval.get("risk_level", "MEDIUM"),
                "summary": ai_eval.get("summary", ""),
                "key_signals": ai_eval.get("key_signals", []),
                "risks": ai_eval.get("risks", []),
                "selling_point": ai_eval.get("selling_point", ""),
                "disclaimer": "AI-generated financial decision support only. Not financial or investment advice.",
            }

            # 4. Log to DB
            await _log_analysis_to_db(stock_result, cur_date)

            results.append(SingleStockAnalysisResponse(**stock_result))
        except Exception as e:
            # Continue analyzing others if one ticker fails
            continue

    if not results:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze requested stocks: {tickers_to_analyze}",
        )

    return results
