import datetime
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from sqlalchemy.future import select
from app.database import AsyncSessionLocal
from app.models.stock_models import StockAnalysisSnapshot

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/today")
async def get_todays_analysis(ticker: Optional[str] = None):
    """Returns today's analysis snapshots for Indian stocks from the DB."""
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as session:
        query = select(StockAnalysisSnapshot).where(
            StockAnalysisSnapshot.analysis_date == today_str
        ).order_by(StockAnalysisSnapshot.created_at.desc())
        if ticker:
            query = query.where(StockAnalysisSnapshot.symbol == ticker.strip().upper())
        result = await session.execute(query)
        rows = result.scalars().all()

        data = []
        for r in rows:
            data.append({
                "id": r.id,
                "ticker": r.ticker,
                "symbol": r.symbol,
                "name": r.name,
                "analysis_date": r.analysis_date,
                "initial_price": r.initial_price,
                "target_price": r.target_price,
                "stop_loss": r.stop_loss,
                "overall_sentiment": r.overall_sentiment,
                "intraday_bias": r.intraday_bias,
                "recommendation": r.recommendation,
                "technical_score": r.technical_score,
                "macro_score": r.macro_score,
                "ai_reasoning": r.ai_reasoning,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })
        return {"date": today_str, "count": len(data), "results": data}


@router.get("/prediction")
async def get_prediction_by_date(
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    ticker: Optional[str] = None
):
    """Fetch AI prediction and analysis snapshots for any particular date."""
    async with AsyncSessionLocal() as session:
        query = select(StockAnalysisSnapshot).where(
            StockAnalysisSnapshot.analysis_date == date
        ).order_by(StockAnalysisSnapshot.created_at.desc())
        if ticker:
            query = query.where(StockAnalysisSnapshot.symbol == ticker.strip().upper())
        result = await session.execute(query)
        rows = result.scalars().all()

        data = []
        for r in rows:
            data.append({
                "id": r.id,
                "ticker": r.ticker,
                "symbol": r.symbol,
                "name": r.name,
                "analysis_date": r.analysis_date,
                "initial_price": r.initial_price,
                "target_price": r.target_price,
                "stop_loss": r.stop_loss,
                "overall_sentiment": r.overall_sentiment,
                "intraday_bias": r.intraday_bias,
                "recommendation": r.recommendation,
                "technical_score": r.technical_score,
                "macro_score": r.macro_score,
                "ai_reasoning": r.ai_reasoning,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })
        return {"date": date, "count": len(data), "results": data}


@router.post("/log")
async def log_analysis_snapshot(payload: dict):
    """Save/Log an AI prediction snapshot for a specific date and ticker."""
    required = ["ticker", "symbol", "analysis_date", "initial_price"]
    for f in required:
        if f not in payload:
            raise HTTPException(status_code=400, detail=f"Missing required field: {f}")

    async with AsyncSessionLocal() as session:
        snap = StockAnalysisSnapshot(
            ticker=payload["ticker"].strip().upper(),
            symbol=payload["symbol"].strip().upper(),
            name=payload.get("name", payload["symbol"]),
            analysis_date=payload["analysis_date"],
            initial_price=float(payload["initial_price"]),
            target_price=float(payload["target_price"]) if payload.get("target_price") else None,
            stop_loss=float(payload["stop_loss"]) if payload.get("stop_loss") else None,
            overall_sentiment=payload.get("overall_sentiment", "Neutral"),
            intraday_bias=payload.get("intraday_bias", "Neutral"),
            recommendation=payload.get("recommendation", "HOLD"),
            technical_score=float(payload.get("technical_score", 50.0)),
            macro_score=float(payload.get("macro_score", 50.0)),
            ai_reasoning=payload.get("ai_reasoning"),
            structured_json=payload.get("structured_json"),
        )
        session.add(snap)
        await session.commit()
        await session.refresh(snap)
        return {"message": "Analysis snapshot saved.", "id": snap.id, "analysis_date": snap.analysis_date}
