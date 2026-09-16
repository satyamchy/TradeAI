from typing import Optional
from pydantic import BaseModel


class JobCreateRequest(BaseModel):
    """
    Scheduled Job Creation Payload.

    - title (str): Friendly title (e.g. 'Pre-Market NIFTY50 scan')
    - job_type (str, optional): 'CRON' or 'NORMAL' (default 'CRON')
    - tickers (str): Comma-separated symbols (e.g. 'RELIANCE.NS,TCS.NS,INFY.NS')
    - cron_expression (str, optional): Standard 5-field cron string (default '15 9 * * 1-5')
    - market_hours_only (bool, optional): True to restrict execution to 9:15-15:30 IST
    """
    title: str
    job_type: Optional[str] = "CRON"
    tickers: str
    cron_expression: Optional[str] = "15 9 * * 1-5"
    market_hours_only: Optional[bool] = True
