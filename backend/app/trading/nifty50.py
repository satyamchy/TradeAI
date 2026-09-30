"""NIFTY 50 trading symbols.

This list is the only universe the automation will trade. It reconstitutes
when NSE changes the index, so it has to be checked against the live
constituents rather than treated as permanent.
"""

NIFTY50_SYMBOLS: tuple[str, ...] = (
    "ADANIENT",
    "ADANIPORTS",
    "APOLLOHOSP",
    "ASIANPAINT",
    "AXISBANK",
    "BAJAJ-AUTO",
    "BAJFINANCE",
    "BAJAJFINSV",
    "BEL",
    "BHARTIARTL",
    "CIPLA",
    "COALINDIA",
    "DRREDDY",
    "EICHERMOT",
    "GRASIM",
    "HCLTECH",
    "HDFCBANK",
    "HDFCLIFE",
    "HEROMOTOCO",
    "HINDALCO",
    "HINDUNILVR",
    "ICICIBANK",
    "ITC",
    "INDUSINDBK",
    "INFY",
    "JSWSTEEL",
    "KOTAKBANK",
    "LT",
    "LTIM",
    "M&M",
    "MARUTI",
    "NESTLEIND",
    "NTPC",
    "ONGC",
    "POWERGRID",
    "RELIANCE",
    "SBILIFE",
    "SBIN",
    "SUNPHARMA",
    "TCS",
    "TATACONSUM",
    "TATAMOTORS",
    "TATASTEEL",
    "TECHM",
    "TITAN",
    "TRENT",
    "ULTRACEMCO",
    "UPL",
    "WIPRO",
    "SHRIRAMFIN",
)

NIFTY50_SET = frozenset(NIFTY50_SYMBOLS)


def normalize_symbol(symbol: str) -> str:
    """Upper-case NSE symbol without a .NS or .BO suffix."""
    return symbol.upper().replace(".NS", "").replace(".BO", "").strip()


def is_nifty50_symbol(symbol: str) -> bool:
    """True when `symbol` is in the NIFTY 50 list this process trades."""
    return normalize_symbol(symbol) in NIFTY50_SET
