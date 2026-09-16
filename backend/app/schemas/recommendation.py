from typing import List, Optional
from pydantic import BaseModel, Field


class TradeRecommendationRequest(BaseModel):
    """
    - ticker (str): e.g. 'RELIANCE.NS'
    - quantity (int, optional): Quantity the user is considering — used to size the
      margin/order-value precondition checks. Defaults to a small illustrative size
      if omitted, since this endpoint recommends, it never executes.
    """
    ticker: str
    quantity: Optional[int] = Field(default=1, description="Quantity under consideration, for margin/value checks")
    product_type: str = Field(default="INTRADAY", description="INTRADAY or DELIVERY")


class TradeRecommendationResponse(BaseModel):
    """
    - decision: 'BUY' or 'DO_NOT_BUY' — a recommendation only, nothing is executed.
    - blocking_reasons: precondition failures (margin, existing position, etc.)
      that contributed to a DO_NOT_BUY, if any.
    """
    ticker: str
    decision: str
    confidence: float
    reasoning: str
    risk_level: str
    blocking_reasons: List[str] = Field(default_factory=list)
    key_signals: List[str] = Field(default_factory=list)
    disclaimer: str = "AI-generated decision support only. Not financial advice. No order was placed."
