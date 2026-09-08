from datetime import datetime

from pydantic import BaseModel


class Evidence(BaseModel):
    claim: str
    source_url: str
    source_title: str | None = None
    source_type: str  # "web" | "financial_provider" | "news"
    retrieved_at: datetime
    published_at: datetime | None = None
    confidence: float | None = None
