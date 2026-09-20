from pydantic import BaseModel


class StockQuote(BaseModel):
    symbol: str
    name: str
    current_price: float | None
    previous_close: float | None
    day_high: float | None
    day_low: float | None
    volume: int
    currency: str


class AnalyzeRequest(BaseModel):
    query: str  # e.g. "analyze tcs", "should I buy reliance", "infosys stock"


class AnalyzeResponse(BaseModel):
    query: str
    resolved_ticker: str
    resolution_confidence: str  # "llm_resolved"
    quote: StockQuote
    analysis: str
    stock_history: dict  # the raw market data returned by yfinance, for debugging and transparency