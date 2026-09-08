from fastapi import APIRouter
from app.services.performance_tracker import evaluate_performance_history

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


@router.get("/{ticker}/performance")
async def get_performance_history(ticker: str):
    """Fetches past AI analysis snapshots for a stock and compares them with current live market price."""
    return await evaluate_performance_history(ticker)
