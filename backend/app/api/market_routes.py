from fastapi import APIRouter
from app.services.market_data_service import get_indian_market_status, get_indian_indices_summary

router = APIRouter(prefix="/market", tags=["market"])

@router.get("/status")
async def market_status():
    """Returns current Indian stock market clock in IST, open status, and trading hours."""
    return get_indian_market_status()

@router.get("/indices")
async def market_indices():
    """Returns live market indices summary (NIFTY 50, BANKNIFTY, SENSEX, GOLDBEES, SILVERBEES)."""
    return get_indian_indices_summary()
