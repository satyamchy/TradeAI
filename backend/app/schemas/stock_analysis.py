from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class StockAnalyzeRequest(BaseModel):
    """
    Stock Analysis Request Payload.

    - mode (str): 'selected' (analyze specific tickers) or 'top_movers' (analyze top intraday gainers)
    - symbols (List[str], optional): Tickers or company names (e.g. ['RELIANCE.NS', 'TCS'])
    - analysis_type (str): 'intraday' or 'delivery' (default 'intraday')
    - date (str, optional): 'YYYY-MM-DD' analysis reference date
    - top_n (int, optional): Number of top movers to fetch if mode='top_movers' (default 5)
    """
    mode: str = Field(default="selected", description="selected | top_movers")
    symbols: Optional[List[str]] = Field(default=None, description="List of tickers or stock names")
    analysis_type: str = Field(default="intraday", description="intraday | delivery")
    date: Optional[str] = Field(default=None, description="YYYY-MM-DD date string")
    top_n: Optional[int] = Field(default=5, description="Number of top movers if mode='top_movers'")


class SingleStockAnalysisResponse(BaseModel):
    """
    Stock Analysis Result Item.

    - recommendation: 'BUY', 'HOLD', or 'AVOID'
    - confidence: 0.0-1.0
    - risk_level: 'LOW', 'MEDIUM', or 'HIGH'
    """
    symbol: str
    analysis_type: str
    market_data: Dict[str, Any]
    technical_analysis: Dict[str, Any]
    recommendation: str
    confidence: float
    risk_level: str
    summary: str
    key_signals: List[str]
    risks: List[str]
    selling_point: str
    disclaimer: str = "AI-generated financial decision support only. Not financial or investment advice."
