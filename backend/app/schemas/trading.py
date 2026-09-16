"""Schemas for the simplified trading API."""

from typing import Optional, Literal
from pydantic import BaseModel, Field


class OrderRequest(BaseModel):
    symbol: str = Field(min_length=1)
    side: Literal["BUY", "SELL"]
    quantity: int = Field(gt=0)
    order_type: Literal["MARKET", "LIMIT"] = "MARKET"
    product_type: Literal["INTRADAY", "DELIVERY"] = "INTRADAY"
    price: float = Field(default=0, ge=0)
    source: Literal["frontend", "llm"] = "frontend"
    notes: Optional[str] = None


class AIPendingTrade(BaseModel):
    symbol: str = Field(min_length=1)
    side: Optional[Literal["BUY", "SELL"]] = None
    quantity: int = Field(gt=0)
    product_type: Literal["INTRADAY", "DELIVERY"] = "INTRADAY"
    order_type: Literal["MARKET", "LIMIT"] = "MARKET"
    price: float = Field(default=0, ge=0)
    prompt: Optional[str] = None


class AIConfirmRequest(BaseModel):
    order_id: int


class AIAnalysisRequest(BaseModel):
    symbol: str = Field(min_length=1)
    analysis_type: Literal["intraday", "delivery"] = "intraday"


class AITradeRequest(BaseModel):
    symbol: str = Field(min_length=1)
    quantity: int = Field(default=1, gt=0)
    product_type: Literal["INTRADAY", "DELIVERY"] = "INTRADAY"
    prompt: Optional[str] = None
    side: Optional[Literal["BUY", "SELL"]] = None
