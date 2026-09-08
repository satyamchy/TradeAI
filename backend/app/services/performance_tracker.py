import logging
import datetime
from sqlalchemy.future import select
from app.database import AsyncSessionLocal, init_db
from app.models.stock_models import StockAnalysisSnapshot
from app.tools.finance.provider_factory import get_provider

logger = logging.getLogger(__name__)


async def save_snapshot_from_data(data: dict) -> StockAnalysisSnapshot | None:
    """Saves a timestamped analysis snapshot to the database."""
    if not data or not data.get("ticker"):
        return None

    ticker = data.get("ticker", "").upper()
    symbol = data.get("symbol") or ticker.replace(".NS", "")
    name = data.get("name") or symbol
    initial_price = data.get("current_price") or 0.0

    indicators = data.get("indicators", {})
    period_return = indicators.get("period_return_pct")

    # Extract intraday bias or sentiment
    intraday = data.get("intraday_assessment", {})
    intraday_bias = intraday.get("bias") if isinstance(intraday, dict) else "Neutral"
    overall_sentiment = data.get("overall_sentiment", "Neutral")

    try:
        await init_db()
        async with AsyncSessionLocal() as session:
            snapshot = StockAnalysisSnapshot(
                ticker=ticker,
                symbol=symbol,
                name=name,
                initial_price=initial_price,
                currency=data.get("currency", "INR"),
                overall_sentiment=overall_sentiment,
                intraday_bias=intraday_bias,
                period_return_pct=period_return,
                structured_json=data,
                created_at=datetime.datetime.utcnow(),
            )
            session.add(snapshot)
            await session.commit()
            await session.refresh(snapshot)
            logger.info("SNAPSHOT_SAVED | ticker=%s | price=%s", ticker, initial_price)
            return snapshot
    except Exception as e:
        logger.exception("FAILED_SAVE_SNAPSHOT | ticker=%s | error=%s", ticker, e)
        return None


async def evaluate_performance_history(ticker: str) -> dict:
    """Compares past AI analysis snapshots against current live price to measure accuracy."""
    ticker_clean = ticker.strip().upper()
    if not ticker_clean.endswith(".NS") and "^" not in ticker_clean:
        ticker_clean = f"{ticker_clean}.NS"

    try:
        await init_db()
        async with AsyncSessionLocal() as session:
            stmt = (
                select(StockAnalysisSnapshot)
                .where(StockAnalysisSnapshot.ticker == ticker_clean)
                .order_by(StockAnalysisSnapshot.created_at.desc())
            )
            result = await session.execute(stmt)
            snapshots = result.scalars().all()

        if not snapshots:
            return {
                "ticker": ticker_clean,
                "has_history": False,
                "message": f"No past analysis snapshot recorded for {ticker_clean} yet.",
                "history": [],
            }

        # Fetch live current market price
        provider = get_provider()
        quote = await provider.get_quote(ticker_clean)
        live_price = quote.get("current_price") or snapshots[0].initial_price

        performance_history = []
        correct_predictions = 0

        for snap in snapshots:
            old_price = snap.initial_price
            price_change = round(live_price - old_price, 2)
            actual_return_pct = round(((live_price - old_price) / old_price * 100), 2) if old_price > 0 else 0.0

            # Evaluate whether AI prediction was correct
            bias = snap.intraday_bias or snap.overall_sentiment or "Neutral"
            is_successful = (
                (bias in ["Bullish", "Positive", "Strong Positive"] and actual_return_pct >= 0) or
                (bias in ["Bearish", "Negative", "Strong Negative"] and actual_return_pct <= 0) or
                (bias == "Neutral" and abs(actual_return_pct) < 1.0)
            )

            if is_successful:
                correct_predictions += 1

            performance_history.append({
                "snapshot_id": snap.id,
                "analyzed_at": snap.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "initial_price": old_price,
                "current_price": live_price,
                "price_change": price_change,
                "actual_return_pct": actual_return_pct,
                "ai_bias": bias,
                "expected_period_return_pct": snap.period_return_pct,
                "prediction_successful": is_successful,
            })

        accuracy_score_pct = round((correct_predictions / len(snapshots) * 100), 1)

        return {
            "ticker": ticker_clean,
            "has_history": True,
            "total_snapshots": len(snapshots),
            "live_current_price": live_price,
            "overall_ai_accuracy_score_pct": accuracy_score_pct,
            "trust_rating": "High Trust" if accuracy_score_pct >= 70 else ("Moderate Trust" if accuracy_score_pct >= 50 else "Evaluating"),
            "history": performance_history,
        }
    except Exception as e:
        logger.exception("EVALUATE_PERFORMANCE_FAILED | ticker=%s | error=%s", ticker, e)
        return {
            "ticker": ticker,
            "has_history": False,
            "error": str(e),
            "history": [],
        }
