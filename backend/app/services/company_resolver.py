# """
# Resolves free-text company references to canonical NSE tickers.
# Order of resolution:
#   1. Alias dict (fast path for the ~50 most common names)
#   2. Exact symbol match against the live Dhan security master
#   3. Fuzzy match against the security master (high-confidence only)
# No LLM step here — this is the lightweight path used by /quote and /history.
# Ambiguous free-text with no clear winner raises CompanyResolutionError;
# callers should surface a 404 with the message, not guess.
# """

# import re

# from app.services.security_master_index import security_index
# from app.schemas.finance.company import CompanyEntity
# from app.services.market_data_service import fetch_stock_market_data

# # Canonical Indian market aliases
# COMMON_INDIAN_ALIASES = {
#     "nifty": "^NSEI",
#     "nifty 50": "^NSEI",
#     "nifty50": "^NSEI",
#     "banknifty": "^NSEBANK",
#     "nifty bank": "^NSEBANK",
#     "sensex": "^BSESN",
#     "goldbees": "GOLDBEES.NS",
#     "silverbees": "SILVERBEES.NS",
#     "reliance": "RELIANCE.NS",
#     "reliance industries": "RELIANCE.NS",
#     "ril": "RELIANCE.NS",
#     "tcs": "TCS.NS",
#     "tata consultancy services": "TCS.NS",
#     "infosys": "INFY.NS",
#     "infy": "INFY.NS",
#     "hcl tech": "HCLTECH.NS",
#     "hcltech": "HCLTECH.NS",
#     "wipro": "WIPRO.NS",
#     "hdfc": "HDFCBANK.NS",
#     "hdfc bank": "HDFCBANK.NS",
#     "hdfcbank": "HDFCBANK.NS",
#     "icici": "ICICIBANK.NS",
#     "icici bank": "ICICIBANK.NS",
#     "icicibank": "ICICIBANK.NS",
#     "sbi": "SBIN.NS",
#     "state bank of india": "SBIN.NS",
#     "sbin": "SBIN.NS",
#     "tata motors": "TATAMOTORS.NS",
#     "tatamotors": "TATAMOTORS.NS",
#     "tata steel": "TATASTEEL.NS",
#     "tatasteel": "TATASTEEL.NS",
#     "maruti": "MARUTI.NS",
#     "maruti suzuki": "MARUTI.NS",
#     "lt": "LT.NS",
#     "l&t": "LT.NS",
#     "larsen & toubro": "LT.NS",
#     "axis bank": "AXISBANK.NS",
#     "axisbank": "AXISBANK.NS",
#     "sun pharma": "SUNPHARMA.NS",
#     "sunpharma": "SUNPHARMA.NS",
#     "bajaj finance": "BAJFINANCE.NS",
#     "bajfinance": "BAJFINANCE.NS",
#     "itc": "ITC.NS",
#     "kotak": "KOTAKBANK.NS",
#     "kotak bank": "KOTAKBANK.NS",
#     "bharti airtel": "BHARTIARTL.NS",
#     "airtel": "BHARTIARTL.NS",
#     "ntpc": "NTPC.NS",
#     "ongc": "ONGC.NS",
#     "powergrid": "POWERGRID.NS",
#     "coal india": "COALINDIA.NS",
#     "adani enterprises": "ADANIENT.NS",
#     "adanient": "ADANIENT.NS",
#     "adani ports": "ADANIPORTS.NS",
#     "adaniports": "ADANIPORTS.NS",
#     "titan": "TITAN.NS",
#     "ultratech": "ULTRACEMCO.NS",
#     "asian paints": "ASIANPAINT.NS",
#     "zomato": "ZOMATO.NS",
# }

# FUZZY_ACCEPT_THRESHOLD = 90.0
# FUZZY_MARGIN = 15.0  # winner must beat runner-up by this much to be "confident"

# class CompanyResolutionError(Exception):
#     pass

# def clean_stock_query(text: str) -> str:
#     """Strips common phrases like 'Analyze ', 'Stock of ', 'Share of '."""
#     s = text.strip()
#     s = re.sub(r"^(analyze|analyse|check|predict|evaluate|fetch|get)\s+", "", s, flags=re.IGNORECASE)
#     s = re.sub(r"\b(stock|share|equity|ltd|limited)\b", "", s, flags=re.IGNORECASE)
#     return s.strip()


# def resolve_ticker_symbol(text: str) -> str:
#     """
#     Returns a yfinance-compatible ticker string ("TCS.NS") or raises
#     CompanyResolutionError. Never falls back to a blind '<UPPER>.NS' guess —
#     that's the exact failure mode that produced silent bad data before.
#     """
#     cleaned = clean_stock_query(text)
#     key = cleaned.lower()

#     # 1. alias fast path
#     if key in COMMON_INDIAN_ALIASES:
#         return COMMON_INDIAN_ALIASES[key]

#     # already looks like a real ticker/index the caller typed directly
#     raw_upper = cleaned.upper().replace(" ", "")
#     if raw_upper.endswith((".NS", ".BO")) or raw_upper.startswith("^"):
#         return raw_upper

#     # 2. exact symbol match against real instrument master
#     if security_index.is_ready():
#         exact = security_index.exact_symbol(cleaned)
#         if exact:
#             return f"{exact.symbol}.NS"

#         # 3. fuzzy match — only accept a clear, confident winner
#         matches = security_index.search(cleaned, limit=5)
#         if matches:
#             top_record, top_score = matches[0]
#             runner_up_score = matches[1][1] if len(matches) > 1 else 0.0
#             if top_score >= FUZZY_ACCEPT_THRESHOLD and (top_score - runner_up_score) >= FUZZY_MARGIN:
#                 return f"{top_record.symbol}.NS"

#     raise CompanyResolutionError(
#         f"Could not confidently resolve '{text}' to a known NSE instrument."
#     )


# async def resolve_company(text: str) -> CompanyEntity:
#     ticker = resolve_ticker_symbol(text)
#     try:
#         market_data = await fetch_stock_market_data(ticker)
#         quote = market_data.get("quote", {})
#         fundamentals = market_data.get("fundamentals", {})
#         name = quote.get("name") or ticker.replace(".NS", "")
#         sector = fundamentals.get("sector")
#         industry = fundamentals.get("industry")
#     except Exception:
#         name = ticker.replace(".NS", "")
#         sector = None
#         industry = None

#     return CompanyEntity(
#         name=name,
#         ticker=ticker,
#         exchange="NSE",
#         country="India",
#         sector=sector,
#         industry=industry,
#     )


# async def resolve_companies(texts: list[str]) -> list[CompanyEntity]:
#     entities = []
#     for text in texts:
#         try:
#             entities.append(await resolve_company(text))
#         except Exception:
#             ticker = resolve_ticker_symbol(text)
#             entities.append(CompanyEntity(name=ticker.replace(".NS", ""), ticker=ticker, exchange="NSE", country="India"))
#     return entities


# from rapidfuzz import process, fuzz

# class SecurityIndex:
#     def __init__(self):
#         self._rows: list[dict] = []  # {name, symbol, security_id, exchange, segment}

#     def build(self, security_master: list[dict]):
#         self._rows = security_master

#     def search(self, query: str, limit: int = 5):
#         choices = {i: row["name"] for i, row in enumerate(self._rows)}
#         matches = process.extract(query, choices, scorer=fuzz.WRatio, limit=limit)
#         return [
#             {**self._rows[idx], "score": score}
#             for _, score, idx in matches
#         ]

# security_index = SecurityIndex()  # populate on refresh_security_master()


# async def resolve_company_v2(text: str, allow_llm_disambiguation: bool = False) -> dict:
#     cleaned = clean_stock_query(text)

#     # 1. fast alias path (keep existing dict as a cache)
#     if cleaned.lower() in COMMON_INDIAN_ALIASES:
#         ticker = COMMON_INDIAN_ALIASES[cleaned.lower()]
#         return {"ticker": ticker, "confidence": "exact"}

#     # 2. fuzzy match against real instrument master
#     candidates = security_index.search(cleaned, limit=5)
#     if not candidates:
#         raise CompanyResolutionError(f"No match found for '{text}'")

#     top = candidates[0]
#     if top["score"] >= 90 and (len(candidates) == 1 or top["score"] - candidates[1]["score"] > 15):
#         return {"ticker": f"{top['symbol']}.NS", "security_id": top["security_id"], "confidence": "high"}

#     if top["score"] >= 90 and clear_winner:
#         return {"confidence": "high", "instrument": build_instrument(top)}

#     if allow_llm_disambiguation:
#         idx = await llm_disambiguate(text, candidates)
#         return {"confidence": "llm_disambiguated", "instrument": build_instrument(candidates[idx])}

#     return {"confidence": "ambiguous", "candidates": candidates}
#     # 3. ambiguous -> LLM picks from the candidate list only
#     choice_idx = await allow_llm_disambiguation(query=text, candidates=candidates)
#     if choice_idx not in range(len(candidates)):
#         raise CompanyResolutionError(f"Could not disambiguate '{text}'")
#     chosen = candidates[choice_idx]
#     return {"ticker": f"{chosen['symbol']}.NS", "security_id": chosen["security_id"], "confidence": "llm_disambiguated"}
