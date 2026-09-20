from enum import Enum
from pydantic import BaseModel


class TradeAction(str, Enum):
    BUY = "BUY"
    AVOID = "AVOID"
    WATCH = "WATCH"  # neutral/unclear signal, no action


class TradeType(str, Enum):
    INTRADAY = "INTRADAY"
    DELIVERY = "DELIVERY"
    NONE = "NONE"


class TradeRecommendation(BaseModel):
    action: TradeAction
    trade_type: TradeType
    entry_price_cap: float | None      # max price willing to buy at
    stop_loss: float | None            # selling cap on the downside
    target_price: float | None         # selling cap on the upside
    confidence: str                    # "low" | "medium" | "high"
    reasoning: str
    buy_flag: bool                     # derived: action == BUY and confidence != low


class RecommendRequest(BaseModel):
    query: str
    quantity: int = 1
    execute: bool = False              # must be explicitly true to place a real order


class ExecutionResult(BaseModel):
    attempted: bool
    executed: bool
    reason: str
    order_id: str | None = None


class RecommendResponse(BaseModel):
    query: str
    resolved_ticker: str
    quote: dict
    recommendation: TradeRecommendation
    execution: ExecutionResult