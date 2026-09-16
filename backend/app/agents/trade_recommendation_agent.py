"""
Trade recommendation agent.

This is the "agent loop" step of the flow:
    stock -> market/technical analysis -> Dhan account context -> [agent loop] -> precondition & risk checks -> BUY / DO_NOT_BUY

It takes already-computed technical analysis and a small, sanitized account
context (available margin, whether a position is already open — never
credentials or tokens) and asks the LLM for one structured decision. It
never calls Dhan or places an order itself.

The LLM's decision is not the final word: app.controllers.trade_recommendation_controller
runs app.guardrails.preconditions.check_preconditions() on the result and can
force a BUY down to DO_NOT_BUY if a hard constraint (insufficient margin, an
already-open position) is violated — the same principle used everywhere else
in this codebase: the LLM interprets and reasons, deterministic code has the
final safety say.
"""

import json
import re
import logging
from typing import Any, Dict

from langchain_core.messages import SystemMessage, HumanMessage

from app.integrations.llm.groq_client import get_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a disciplined trade-recommendation agent for Indian equities.

You will be given: a ticker, its current technical analysis (trend, RSI, MACD,
support/resistance, volatility), and account context (available margin, whether
a position is already open in this symbol). You do not have fundamental data
here — this is a short-horizon (intraday/short-term) call.

CRITICAL RULES:
1. STRICT GROUNDING: only use the numbers provided. Never invent a price,
   indicator value, or margin figure.
2. DECISION: exactly one of "BUY" or "DO_NOT_BUY". There is no middle option —
   if you are not confident, DO_NOT_BUY is the correct, safe answer.
3. If the account context shows a position is already open in this symbol, or
   available margin looks tight relative to a typical order, factor that into
   your decision and say so in the reasoning — a separate deterministic check
   also enforces this afterward, but you should still reason about it.
4. CONFIDENCE: a float between 0.0 and 1.0.
5. RISK_LEVEL: exactly one of "LOW", "MEDIUM", "HIGH".
6. Give 2-4 KEY_SIGNALS as short factual observations grounded in the provided data.

Respond ONLY with a valid JSON object, no markdown fences:
{
  "decision": "BUY" | "DO_NOT_BUY",
  "confidence": 0.72,
  "risk_level": "LOW" | "MEDIUM" | "HIGH",
  "reasoning": "2-3 sentences grounded in the provided numbers.",
  "key_signals": ["...", "..."]
}
"""


def _rule_based_fallback(technical_summary: Dict[str, Any], account_context: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic fallback if the LLM call fails — keeps the endpoint
    available even if Groq is down, same pattern as ai_analysis_service."""
    rsi = technical_summary.get("rsi_14") or 50.0
    trend = (technical_summary.get("trend") or "NEUTRAL").upper()
    has_open_position = account_context.get("has_open_position", False)

    if has_open_position:
        return {
            "decision": "DO_NOT_BUY",
            "confidence": 0.6,
            "risk_level": "MEDIUM",
            "reasoning": "A position is already open in this symbol; fallback rule avoids doubling up.",
            "key_signals": ["Existing open position detected"],
        }

    if rsi >= 60 and "BULLISH" in trend:
        return {
            "decision": "BUY",
            "confidence": 0.6,
            "risk_level": "MEDIUM",
            "reasoning": f"Fallback rule: RSI {rsi} with a bullish trend.",
            "key_signals": [f"RSI (14) at {rsi}", f"Trend: {trend}"],
        }

    return {
        "decision": "DO_NOT_BUY",
        "confidence": 0.55,
        "risk_level": "MEDIUM",
        "reasoning": f"Fallback rule: RSI {rsi} / trend {trend} did not clear the bullish bar.",
        "key_signals": [f"RSI (14) at {rsi}", f"Trend: {trend}"],
    }


async def generate_recommendation(
    ticker: str,
    technical_summary: Dict[str, Any],
    account_context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    account_context is the sanitized dict the controller builds — expected
    keys: available_margin (float), has_open_position (bool). Never pass
    tokens/credentials in here; this function only ever sees numbers.
    """
    user_payload = {
        "ticker": ticker,
        "technical_summary": technical_summary,
        "account_context": account_context,
    }
    user_prompt = f"Evaluate {ticker} for a BUY / DO_NOT_BUY call:\n" + json.dumps(user_payload, indent=2)

    try:
        llm = get_llm()
        response = await llm.ainvoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_prompt)])
        content = response.content.strip()
        content = re.sub(r"^```(json)?", "", content, flags=re.MULTILINE)
        content = re.sub(r"```$", "", content, flags=re.MULTILINE).strip()

        parsed = json.loads(content)
        decision = parsed.get("decision", "DO_NOT_BUY").upper()
        if decision not in ("BUY", "DO_NOT_BUY"):
            decision = "DO_NOT_BUY"
        risk = parsed.get("risk_level", "MEDIUM").upper()
        if risk not in ("LOW", "MEDIUM", "HIGH"):
            risk = "MEDIUM"
        confidence = min(max(float(parsed.get("confidence", 0.5)), 0.0), 1.0)

        return {
            "decision": decision,
            "confidence": round(confidence, 2),
            "risk_level": risk,
            "reasoning": parsed.get("reasoning", ""),
            "key_signals": parsed.get("key_signals", []),
        }
    except Exception as exc:
        logger.warning("Trade recommendation LLM call failed for %s: %s. Using fallback.", ticker, exc)
        return _rule_based_fallback(technical_summary, account_context)
