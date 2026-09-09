"""
Market Status & Benchmark Indices API Router.
Exposes real-time Indian stock market status and key index snapshots.

Endpoints:
- GET /market/status: Current IST market session clock and status.
- GET /market/indices: Key index summary (NIFTY 50, BANKNIFTY, SENSEX, Gold, Silver).
"""

from fastapi import APIRouter
from app.services.market_data_service import get_indian_market_status, get_indian_indices_summary

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/status")
async def market_status():
    """
    Returns current Indian stock market clock in IST, open status, and trading hours.

    - **Purpose**: Real-time session monitoring (Pre-market, Open, Post-market, Closed).
    - **Method**: GET
    - **Payload**: None
    - **Response**:
      ```json
      {
        "current_time_ist": "09:30:15",
        "current_date": "2026-09-10",
        "is_trading_day": true,
        "is_market_open": true,
        "status": "MARKET_OPEN",
        "trading_hours": "09:15 - 15:30 IST"
      }
      ```
    """
    return get_indian_market_status()


@router.get("/indices")
async def market_indices():
    """
    Returns live market indices summary (NIFTY 50, BANKNIFTY, SENSEX, GOLDBEES, SILVERBEES).

    - **Purpose**: Dashboard ticker tape and benchmark performance overview.
    - **Method**: GET
    - **Payload**: None
    - **Response**:
      ```json
      [
        {"symbol": "NIFTY 50", "current_price": 25120.5, "change": 140.2, "change_pct": 0.56},
        {"symbol": "BANKNIFTY", "current_price": 51230.0, "change": -85.4, "change_pct": -0.17}
      ]
      ```
    """
    return get_indian_indices_summary()
