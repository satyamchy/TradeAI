from typing import Optional
from pydantic import BaseModel


class MarketHistoryParams(BaseModel):
    period: str = "1mo"
    interval: str = "1d"
