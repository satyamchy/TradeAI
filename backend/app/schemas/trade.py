"""Schemas for local trade-journal CRUD."""

from typing import Optional
from pydantic import BaseModel


class TradeCreateRequest(BaseModel):
    """
    Manual Trade Creation Payload.

    - trade_date (str): 'YYYY-MM-DD'
    - trade_time (str, optional): 'HH:MM:SS'
    - symbol (str): e.g. 'RELIANCE.NS'
    - trade_type (str): 'BUY' or 'SELL'
    - product_type (str, optional): 'INTRADAY' or 'DELIVERY'
    - asset_category (str, optional): 'STOCK', 'GOLD', or 'SILVER'
    - quantity (int): Units
    - price (float): Execution price (₹)
    - stop_loss / target_price (float, optional)
    - brokerage (float, optional): Estimated charges
    - realized_pnl (float, optional): Closed P&L if already squared off
    - notes (str, optional): Rationale
    """
    trade_date: str
    trade_time: Optional[str] = None
    symbol: str
    trade_type: str
    product_type: Optional[str] = "INTRADAY"
    asset_category: Optional[str] = "STOCK"
    quantity: int
    price: float
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    brokerage: Optional[float] = 0.0
    realized_pnl: Optional[float] = 0.0
    notes: Optional[str] = None

class TradeUpdateRequest(BaseModel):
    """Partial update payload for an existing trade log row."""
    price: Optional[float] = None
    quantity: Optional[int] = None
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    realized_pnl: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None
