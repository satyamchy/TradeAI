from typing import List, Optional
from pydantic import BaseModel, Field


class KeyLevels(BaseModel):
    support: List[float] = Field(default_factory=list, description="Support price levels to watch")
    resistance: List[float] = Field(default_factory=list, description="Resistance price levels to watch")


class IntradayAssessment(BaseModel):
    bias: str = Field(..., description="Bullish, Bearish, or Neutral")
    confidence: str = Field(..., description="Low, Medium, or High")
    risk: str = Field(..., description="Low, Medium, or High")
    key_levels: KeyLevels = Field(default_factory=KeyLevels)
    key_reasons: List[str] = Field(default_factory=list)


class ShortTermAssessment(BaseModel):
    bias: str = Field(..., description="Bullish, Bearish, or Neutral")
    confidence: str = Field(..., description="Low, Medium, or High")
    risk: str = Field(..., description="Low, Medium, or High")
    key_reasons: List[str] = Field(default_factory=list)


class LongTermAssessment(BaseModel):
    suitability: str = Field(..., description="Strong Positive, Positive, Neutral, Negative, or Strong Negative")
    confidence: str = Field(..., description="Low, Medium, or High")
    risk: str = Field(..., description="Low, Medium, or High")
    key_reasons: List[str] = Field(default_factory=list)


class StockAnalysisResponse(BaseModel):
    symbol: str
    name: Optional[str] = None
    current_price: Optional[float] = None
    currency: str = "INR"
    overall_sentiment: str = "Neutral"
    overall_risk_level: str = "Medium"
    overall_confidence: float = 0.70
    technical_score: Optional[float] = None
    fundamental_score: Optional[float] = None
    intraday_assessment: Optional[IntradayAssessment] = None
    short_term_assessment: Optional[ShortTermAssessment] = None
    long_term_assessment: Optional[LongTermAssessment] = None
    key_risks: List[str] = Field(default_factory=list)
    summary: str
    disclaimer: str = "AI-generated analysis and decision support only. Not financial advice."
