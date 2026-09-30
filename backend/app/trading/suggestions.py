"""One LLM suggestion, checked against the screener rows we just computed.

The model may return a symbol and a side. Quantity and price come from
the screener and the risk limits. This module does not place orders.
"""

from __future__ import annotations

import json

import httpx

from app.config import settings
from app.trading.risk_limits import RiskLimits, build_entry_plan
from app.trading.screener import rank_nifty50


def accept_model_choice(raw: str, choices: list[dict]) -> dict | None:
    """Return the picked row, or None when the reply is not one of `choices`.

    Each choice has `symbol`, `side` (BUY or SELL), and `ltp` in INR.
    Extra fields from the model are ignored. A symbol it invented is dropped.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.removeprefix("json").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    symbol = str(data.get("symbol", "")).upper().strip()
    side = str(data.get("side", "")).upper().strip()
    for choice in choices:
        if choice["symbol"] == symbol and choice["side"] == side:
            return {"symbol": symbol, "side": side, "price": float(choice["ltp"])}
    return None


async def build_suggestion(limits: RiskLimits, balance_inr: float, open_positions: int) -> dict:
    """Ask for one pick and size it. Raises ValueError when nothing valid comes back.

    The returned dict is a pending order payload. It is not an order.
    """
    long_rows = await rank_nifty50("long", limit=limits.screener_limit)
    short_rows = await rank_nifty50("short", limit=limits.screener_limit)
    choices = [{"symbol": row["symbol"], "side": "BUY", "ltp": row["ltp"]} for row in long_rows]
    choices += [{"symbol": row["symbol"], "side": "SELL", "ltp": row["ltp"]} for row in short_rows]
    if not choices:
        raise ValueError("The screener returned no names to choose from")
    if not settings.groq_api_key:
        raise ValueError("GROQ_API_KEY is not set")

    picked = accept_model_choice(await _ask(choices), choices)
    if picked is None:
        raise ValueError("The model reply was not one of the offered names")

    method = "intraday_long" if picked["side"] == "BUY" else "intraday_short"
    plan = build_entry_plan(
        balance_inr=balance_inr,
        open_position_count=open_positions,
        candidates_by_method={method: [{"symbol": picked["symbol"], "ltp": picked["price"]}]},
        limits=limits,
    )
    if not plan:
        raise ValueError("Cash or position limits leave no room for this suggestion")
    item = plan[0]
    return {
        "symbol": item["symbol"],
        "side": item["side"],
        "quantity": item["quantity"],
        "price": item["price"],
        "product": "INTRADAY",
        "detail": f"Suggestion from the screener list. Not an order until you execute it.",
    }


async def _ask(choices: list[dict]) -> str:
    """Send the allowed pairs and read the model's text. The prompt forbids new symbols."""
    offered = [{"symbol": choice["symbol"], "side": choice["side"]} for choice in choices]
    prompt = (
        "Reply with one JSON object and nothing else: "
        '{"symbol": "NAME", "side": "BUY" or "SELL"}. '
        "Copy one pair from this list. Do not invent a symbol, a price, or a quantity. "
        f"List: {json.dumps(offered)}"
    )
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            json={
                "model": settings.groq_model,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
    if response.status_code >= 400:
        raise ValueError("The suggestion model did not answer")
    body = response.json()
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("The suggestion model did not answer") from exc
