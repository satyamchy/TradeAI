from pydantic import BaseModel


class CompanyEntity(BaseModel):
    name: str
    ticker: str
    exchange: str | None = None
    country: str | None = None
    sector: str | None = None
    industry: str | None = None

class ResolvedInstrument(BaseModel):
    symbol: str            # "TCS.NS" — for yfinance
    security_id: str       # Dhan's internal id — for order placement
    exchange: str          # "NSE"
    segment: str           # "EQUITY", "INDEX", "ETF" etc from security master
    display_name: str      # "Tata Consultancy Services"
    confidence: str         # "exact" | "high" | "llm_disambiguated"

class ResolveCandidate(BaseModel):
    symbol: str
    security_id: str
    display_name: str
    score: float

class ResolveResponse(BaseModel):
    resolved: ResolvedInstrument | None
    needs_disambiguation: bool
    candidates: list[ResolveCandidate] = []