"""
Resolves free-text company references ("Analyze TCS", "TCS", "Reliance", "INFY")
strictly to canonical Indian NSE/BSE tickers ("TCS.NS", "RELIANCE.NS").
All foreign/global stocks (Apple, Microsoft, etc.) have been removed.
"""

import re
from typing import List, Optional
from app.schemas.finance.company import CompanyEntity
from app.tools.finance.provider_factory import get_provider

# Canonical Indian market aliases
COMMON_INDIAN_ALIASES = {
    "nifty": "^NSEI",
    "nifty 50": "^NSEI",
    "nifty50": "^NSEI",
    "banknifty": "^NSEBANK",
    "nifty bank": "^NSEBANK",
    "sensex": "^BSESN",
    "goldbees": "GOLDBEES.NS",
    "silverbees": "SILVERBEES.NS",
    "reliance": "RELIANCE.NS",
    "reliance industries": "RELIANCE.NS",
    "ril": "RELIANCE.NS",
    "tcs": "TCS.NS",
    "tata consultancy services": "TCS.NS",
    "infosys": "INFY.NS",
    "infy": "INFY.NS",
    "hcl tech": "HCLTECH.NS",
    "hcltech": "HCLTECH.NS",
    "wipro": "WIPRO.NS",
    "hdfc": "HDFCBANK.NS",
    "hdfc bank": "HDFCBANK.NS",
    "hdfcbank": "HDFCBANK.NS",
    "icici": "ICICIBANK.NS",
    "icici bank": "ICICIBANK.NS",
    "icicibank": "ICICIBANK.NS",
    "sbi": "SBIN.NS",
    "state bank of india": "SBIN.NS",
    "sbin": "SBIN.NS",
    "tata motors": "TATAMOTORS.NS",
    "tatamotors": "TATAMOTORS.NS",
    "tata steel": "TATASTEEL.NS",
    "tatasteel": "TATASTEEL.NS",
    "maruti": "MARUTI.NS",
    "maruti suzuki": "MARUTI.NS",
    "lt": "LT.NS",
    "l&t": "LT.NS",
    "larsen & toubro": "LT.NS",
    "axis bank": "AXISBANK.NS",
    "axisbank": "AXISBANK.NS",
    "sun pharma": "SUNPHARMA.NS",
    "sunpharma": "SUNPHARMA.NS",
    "bajaj finance": "BAJFINANCE.NS",
    "bajfinance": "BAJFINANCE.NS",
    "itc": "ITC.NS",
    "kotak": "KOTAKBANK.NS",
    "kotak bank": "KOTAKBANK.NS",
    "bharti airtel": "BHARTIARTL.NS",
    "airtel": "BHARTIARTL.NS",
    "ntpc": "NTPC.NS",
    "ongc": "ONGC.NS",
    "powergrid": "POWERGRID.NS",
    "coal india": "COALINDIA.NS",
    "adani enterprises": "ADANIENT.NS",
    "adanient": "ADANIENT.NS",
    "adani ports": "ADANIPORTS.NS",
    "adaniports": "ADANIPORTS.NS",
    "titan": "TITAN.NS",
    "ultratech": "ULTRACEMCO.NS",
    "asian paints": "ASIANPAINT.NS",
    "zomato": "ZOMATO.NS",
}


class CompanyResolutionError(Exception):
    pass


def clean_stock_query(text: str) -> str:
    """Strips common phrases like 'Analyze ', 'Stock of ', 'Share of '."""
    s = text.strip()
    s = re.sub(r"^(analyze|analyse|check|predict|evaluate|fetch|get)\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(stock|share|equity|ltd|limited)\b", "", s, flags=re.IGNORECASE)
    return s.strip()


def resolve_ticker_symbol(text: str) -> str:
    """
    Deterministically resolves a single company name or ticker string
    to its canonical Indian symbol (e.g. 'TCS' -> 'TCS.NS').
    """
    cleaned = clean_stock_query(text)
    key = cleaned.lower()

    if key in COMMON_INDIAN_ALIASES:
        return COMMON_INDIAN_ALIASES[key]

    raw_upper = cleaned.upper().replace(" ", "")
    if raw_upper.endswith(".NS") or raw_upper.endswith(".BO") or raw_upper.startswith("^"):
        return raw_upper

    return f"{raw_upper}.NS"


async def resolve_company(text: str) -> CompanyEntity:
    ticker = resolve_ticker_symbol(text)
    provider = get_provider()
    profile = {}
    try:
        profile = await provider.get_company_profile(ticker)
    except Exception:
        profile = {"name": ticker.replace(".NS", ""), "ticker": ticker}

    if not profile.get("name"):
        profile["name"] = ticker.replace(".NS", "")

    return CompanyEntity(
        name=profile.get("name", ticker),
        ticker=profile.get("ticker", ticker),
        exchange=profile.get("exchange", "NSE"),
        country="India",
        sector=profile.get("sector"),
        industry=profile.get("industry"),
    )


async def resolve_companies(texts: list[str]) -> list[CompanyEntity]:
    entities = []
    for text in texts:
        try:
            entities.append(await resolve_company(text))
        except Exception:
            ticker = resolve_ticker_symbol(text)
            entities.append(CompanyEntity(name=ticker.replace(".NS", ""), ticker=ticker, exchange="NSE", country="India"))
    return entities
