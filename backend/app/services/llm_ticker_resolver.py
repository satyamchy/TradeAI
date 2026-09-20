"""
Resolves free text -> a real, yfinance-validated NSE ticker using an LLM,
with a validation + retry loop so a hallucinated symbol never gets used silently.
"""

import json
import logging

import httpx

from app.services.market_data_service import fetch_stock_market_data
from app.integrations.llm.groq_client import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 2

_SYSTEM_PROMPT = """You resolve a user's free-text stock reference to its NSE ticker symbol.
Rules:
- Only Indian companies listed on NSE.
- Respond with ONLY a JSON object, no prose, no markdown fences.
- Format: {"symbol": "TCS", "company_name": "Tata Consultancy Services"}
- "symbol" must be the bare NSE trading symbol WITHOUT ".NS" suffix.
- If you are not confident which company this refers to, respond:
  {"symbol": null, "company_name": null}
"""


class TickerResolutionError(Exception):
    pass


async def _call_llm(user_query: str, prior_attempt_feedback: str | None = None) -> dict:
    messages = [{"role": "user", "content": user_query}]
    if prior_attempt_feedback:
        messages.append({
            "role": "user",
            "content": f"Your previous answer was wrong: {prior_attempt_feedback}. Try again.",
        })

    # async with httpx.AsyncClient(timeout=20.0) as client:
    #     response = await client.post(
    #         "https://api.anthropic.com/v1/messages",
    #         headers={"Content-Type": "application/json"},
    #         json={
    #             "model": "claude-sonnet-4-6",
    #             "max_tokens": 200,
    #             "system": _SYSTEM_PROMPT,
    #             "messages": messages,
    #         },
    #     )
    llm = get_llm()
    # response = await llm.ainvoke({
    #         "system": _SYSTEM_PROMPT,
    #         "messages": messages,
    #     })
    response = await llm.ainvoke(
    [
        SystemMessage(content=_SYSTEM_PROMPT),
        *[HumanMessage(content=m["content"]) for m in messages],
    ]
    )

    text = response.content
    # response.raise_for_status()
    # data = response.json()    

    # text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise TickerResolutionError(f"LLM returned non-JSON output: {text!r}") from e


def _quote_looks_valid(market_data: dict) -> bool:
    quote = market_data.get("quote", {})
    return bool(quote.get("current_price")) and bool(quote.get("name"))


async def resolve_ticker_via_llm(user_query: str) -> tuple[str, dict]:
    """
    Returns (ticker, market_data) for a validated ticker, or raises
    TickerResolutionError if no confident, data-backed resolution is possible.
    """
    feedback = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        parsed = await _call_llm(user_query, prior_attempt_feedback=feedback)
        symbol = parsed.get("symbol")

        if not symbol:
            raise TickerResolutionError(f"Could not identify a company from: '{user_query}'")

        ticker = f"{symbol.strip().upper()}.NS"

        try:
            market_data = await fetch_stock_market_data(ticker, period="5d", interval="1d")
        except Exception as e:
            logger.warning("yfinance fetch failed for candidate %s (attempt %d): %s", ticker, attempt, e)
            feedback = f"'{ticker}' failed to fetch any market data"
            continue

        if _quote_looks_valid(market_data):
            return ticker, market_data

        feedback = f"'{ticker}' returned no valid price data — it's likely not a real NSE symbol"
        logger.warning("Candidate ticker %s rejected: no valid quote data", ticker)

    raise TickerResolutionError(
        f"Could not resolve '{user_query}' to a verified NSE ticker after {MAX_ATTEMPTS} attempts"
    )