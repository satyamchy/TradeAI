"""
Stock Market Analysis API Router.
Handles single, multi-symbol, and top-mover equity evaluations with automatic database snapshot logging.

Endpoints:
- POST /stocks/analyze: Batch/single stock analysis report generation.
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
    """
    Stock Analysis Request Payload.
    
    Fields:
    - mode (str): 'selected' (analyze specific tickers) or 'top_movers' (analyze top intraday gainers).
    - symbols (List[str], optional): List of tickers or company names (e.g. ['RELIANCE.NS', 'TCS']).
    - analysis_type (str): 'intraday' or 'delivery' (default 'intraday').
    - date (str, optional): 'YYYY-MM-DD' analysis reference date.
    - top_n (int, optional): Number of top movers to fetch if mode='top_movers' (default 5).
    """
    mode: str = Field(default="selected", description="selected | top_movers")
    symbols: Optional[List[str]] = Field(default=None, description="List of tickers or stock names, e.g. ['TCS.NS', 'Analyze Reliance']")
    analysis_type: str = Field(default="intraday", description="intraday | delivery")
    date: Optional[str] = Field(default=None, description="YYYY-MM-DD date string")
    top_n: Optional[int] = Field(default=5, description="Number of top movers to return if mode='top_movers'")


class SingleStockAnalysisResponse(BaseModel):
    """
    Stock Analysis Result Item.
    
    Fields:
    - symbol (str): Resolved ticker symbol.
    - analysis_type (str): 'intraday' or 'delivery'.
    - market_data (Dict): Raw quote, fundamentals, and summary.
    - technical_analysis (Dict): Quantitative RSI, MACD, Pivot Points, Moving Averages.
    - recommendation (str): 'BUY', 'HOLD', or 'AVOID'.
    - confidence (float): Score 0.0 - 1.0.
    - risk_level (str): 'LOW', 'MEDIUM', or 'HIGH'.
    - summary (str): Natural language evaluation summary.
    - key_signals (List[str]): Bullet points of technical indicators triggered.
    - risks (List[str]): Market/technical risk factors.
    - selling_point (str): Primary execution rationale.
    - disclaimer (str): Mandatory compliance disclaimer.
    """
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
    Main Stock Market Analysis & Screener Endpoint.

    - **Purpose**: Evaluates market data, technical indicators, and AI recommendations for single or multi-symbol requests.
    - **Method**: POST
    - **Payload**:
      ```json
      {
        "mode": "selected",
        "symbols": ["TCS.NS", "RELIANCE.NS"],
        "analysis_type": "intraday"
      }
      ```
    - **Response**: List of `SingleStockAnalysisResponse` models.
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
            market_data = await fetch_stock_market_data(ticker)
            tech_analysis = run_technical_analysis(market_data, analysis_type=analysis_type)
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

            await _log_analysis_to_db(stock_result, cur_date)
            results.append(SingleStockAnalysisResponse(**stock_result))
        except Exception:
            continue

    if not results:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze requested stocks: {tickers_to_analyze}",
        )

    return results
