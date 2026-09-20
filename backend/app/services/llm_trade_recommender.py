import json
import httpx

_SYSTEM_PROMPT = """You are a cautious Indian equity (NSE) trade-decision assistant.
Given quote, fundamentals, and recent price history for one stock, decide:
- action: BUY, AVOID, or WATCH (WATCH = signal isn't clear enough to act)
- trade_type: INTRADAY, DELIVERY, or NONE (NONE if action is not BUY)
- entry_price_cap: max price to enter at (null if not BUY)
- stop_loss: exit price on the downside (null if not BUY)
- target_price: exit price on the upside (null if not BUY)
- confidence: "low", "medium", or "high"
- reasoning: 2-4 sentences, plain language, cite the specific data points used

Be conservative. Default to WATCH or AVOID when data is thin, volatile, or contradictory.
Never recommend BUY with "high" confidence purely from a single day's move.
Respond with ONLY a JSON object, no prose, no markdown fences:
{"action": "...", "trade_type": "...", "entry_price_cap": ..., "stop_loss": ...,
 "target_price": ..., "confidence": "...", "reasoning": "..."}
"""


class RecommendationError(Exception):
    pass


async def generate_trade_recommendation(ticker: str, market_data: dict) -> dict:
    quote = market_data.get("quote", {})
    fundamentals = market_data.get("fundamentals", {})
    recent_history = market_data.get("history", [])[-10:]  # last 10 candles is enough signal

    user_content = (
        f"Ticker: {ticker}\n"
        f"Quote: {quote}\n"
        f"Fundamentals: {fundamentals}\n"
        f"Recent history (last 10 sessions): {recent_history}\n"
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"Content-Type": "application/json"},
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 500,
                "system": _SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_content}],
            },
        )
        response.raise_for_status()
        data = response.json()

    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise RecommendationError(f"LLM returned non-JSON: {text!r}") from e

    required = {"action", "trade_type", "confidence", "reasoning"}
    if not required.issubset(parsed):
        raise RecommendationError(f"LLM response missing fields: {parsed}")

    parsed["buy_flag"] = parsed["action"] == "BUY" and parsed["confidence"] != "low"
    return parsed