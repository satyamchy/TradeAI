"""Schemas for broker order execution."""

from typing import Optional
from pydantic import BaseModel


class OrderRequest(BaseModel):
    """
    Order Execution Payload.

    - symbol (str): e.g. 'RELIANCE.NS', 'GOLDBEES.NS'
    - trade_type (str): 'BUY' or 'SELL'
    - quantity (int): Number of units / shares
    - price (float): Limit or execution price (₹)
    - product_type (str, optional): 'INTRADAY' or 'DELIVERY' (default 'INTRADAY')
    - asset_category (str, optional): 'STOCK', 'GOLD', or 'SILVER' (default 'STOCK')
    - stop_loss (float, optional): Stop-loss trigger price
    - target_price (float, optional): Profit target price
    - notes (str, optional): Execution comments or AI rationale
    """
    symbol: str
    trade_type: str
    quantity: int
    price: float
    product_type: Optional[str] = "INTRADAY"
    asset_category: Optional[str] = "STOCK"
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    notes: Optional[str] = None

class SquareOffRequest(BaseModel):
    """Square-Off Exit Payload — exit_price (₹) and optional notes."""
    exit_price: float
    notes: Optional[str] = None
