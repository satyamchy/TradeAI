from pydantic import BaseModel


class CompanyEntity(BaseModel):
    name: str
    ticker: str
    exchange: str | None = None
    country: str | None = None
    sector: str | None = None
    industry: str | None = None
