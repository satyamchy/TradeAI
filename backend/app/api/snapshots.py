"""
Historical Snapshots & Accuracy Performance API Router.
Compares past AI analysis snapshots against current live market prices.

Endpoints:
- GET /snapshots/{ticker}/performance: Compares historical AI predictions with live price to compute accuracy score.
"""

from fastapi import APIRouter
from app.services.performance_tracker import evaluate_performance_history

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


@router.get("/{ticker}/performance")
async def get_performance_history(ticker: str):
    """
    Fetches past AI analysis snapshots for a stock and compares them with current live market price.

    - **Purpose**: Computes trust rating and accuracy percentage based on past predictions.
    - **Method**: GET
    - **Path Params**: `ticker` (str, e.g. `RELIANCE.NS`, `TCS`)
    - **Response**:
      ```json
      {
        "ticker": "RELIANCE.NS",
        "has_history": true,
        "total_snapshots": 3,
        "live_current_price": 1294.9,
        "overall_ai_accuracy_score_pct": 66.7,
        "trust_rating": "Moderate Trust",
        "history": [...]
      }
      ```
    """
    return await evaluate_performance_history(ticker)
