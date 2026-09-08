from pydantic import BaseModel, Field


class RouteDecision(BaseModel):
    intent: str = Field(
        description=(
            "One of: GENERAL, WEB_RESEARCH, FINANCIAL_RESEARCH, "
            "COMPANY_ANALYSIS, COMPANY_COMPARISON, PORTFOLIO_ANALYSIS, MARKET_RESEARCH"
        )
    )
    confidence: float = Field(ge=0.0, le=1.0)
    entities: list[str] = Field(
        default_factory=list,
        description="Company names/tickers mentioned, if any (e.g. ['Apple'], ['Apple', 'Microsoft']).",
    )
    reasoning: str | None = None
