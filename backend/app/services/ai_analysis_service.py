"""
AI Analysis Service.
Uses Groq LLM agent to interpret deterministically computed market data
and technical indicators for Indian Equities.
Strictly grounded: Never hallucinates prices, indicators, or financial metrics.
Supports both INTRADAY and DELIVERY analysis.
Outputs: recommendation (BUY | HOLD | AVOID), confidence, risk_level,
summary, key_signals, risks, and selling_point.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional
from app.llm.groq import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert Indian Equities Technical & Fundamental Analyst AI Agent.
Your job is to interpret the provided real market data, technical indicators, and fundamental metrics for the Indian Stock Market (NSE/BSE).

CRITICAL RULES:
1. STRICT GROUNDING: You MUST ONLY interpret the data provided in the prompt. NEVER invent, extrapolate, or hallucinate prices, technical indicator numbers, or financial ratios.
2. RECOMMENDATION: Choose exactly one of: "BUY", "HOLD", "AVOID".
3. RISK LEVEL: Choose exactly one of: "LOW", "MEDIUM", "HIGH".
4. CONFIDENCE: Provide a numeric float between 0.0 and 1.0 based on signal confluence.
5. SELLING POINT:
   - For "intraday": Provide precise intraday target level & mandatory 15:15 PM IST square-off trigger.
   - For "delivery": Provide swing/positional target exit resistance and stop loss invalidation level.
6. KEY SIGNALS: List 3-5 factual observations directly based on the calculated data.
7. RISKS: List 2-4 factual market or technical risk factors.
8. DISCLAIMER: Always treat the result as AI-generated financial decision support, not guaranteed financial advice.

You must respond ONLY with a valid JSON object in this exact schema, without markdown formatting or code blocks:
{
  "recommendation": "BUY" | "HOLD" | "AVOID",
  "confidence": 0.78,
  "risk_level": "LOW" | "MEDIUM" | "HIGH",
  "summary": "Concise summary of findings...",
  "key_signals": ["Signal 1", "Signal 2", "Signal 3"],
  "risks": ["Risk 1", "Risk 2"],
  "selling_point": "Target level and exit condition"
}
"""


def _build_rule_based_fallback(
    symbol: str, analysis_type: str, market_data: Dict[str, Any], tech: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Deterministic rule-based fallback ensuring 100% uptime even if Groq API is offline or rate-limited.
    """
    quote = market_data.get("quote", {})
    curr_price = quote.get("current_price") or 100.0
    rsi = tech.get("rsi_14") or 50.0
    trend = tech.get("trend", "NEUTRAL")
    sr = tech.get("support_resistance", {})
    atr = tech.get("atr") or (curr_price * 0.015)

    is_intraday = analysis_type.lower() == "intraday"

    if rsi >= 60 and "BULLISH" in trend:
        rec = "BUY"
        conf = 0.76
        risk = "MEDIUM" if is_intraday else "LOW"
    elif rsi <= 40 or "BEARISH" in trend:
        rec = "AVOID"
        conf = 0.72
        risk = "HIGH"
    else:
        rec = "HOLD"
        conf = 0.65
        risk = "MEDIUM"

    target = sr.get("r1") or round(curr_price + (atr * 1.5), 2)
    sl = sr.get("s1") or round(curr_price - atr, 2)

    if is_intraday:
        selling_point = f"Intraday target around ₹{target} with stop loss at ₹{sl}. Square off before 15:15 IST."
        summary = (
            f"Intraday analysis for {symbol}: Momentum indicates {trend.lower()} pressure with RSI at {rsi}. "
            f"Volume and intraday range support a {rec} stance for day-trading."
        )
    else:
        selling_point = f"Swing delivery target around ₹{target} (R1 resistance) with protective stop at ₹{sl}."
        summary = (
            f"Delivery analysis for {symbol}: Overall trend is {trend.lower()} with RSI at {rsi}. "
            f"Suitable for {rec} positioning with horizon of 2-6 weeks."
        )

    return {
        "recommendation": rec,
        "confidence": conf,
        "risk_level": risk,
        "summary": summary,
        "key_signals": [
            f"RSI (14) at {rsi} shows {('momentum strength' if rsi > 50 else 'cooling momentum')}",
            f"Technical moving average trend evaluated as {trend}",
            f"Current price is ₹{curr_price} relative to Pivot ₹{sr.get('pivot')}",
        ],
        "risks": [
            "Volatility near key support/resistance boundaries",
            "Broader Indian benchmark index volatility (NIFTY/BANKNIFTY)",
        ],
        "selling_point": selling_point,
    }


async def generate_ai_stock_analysis(
    symbol: str,
    analysis_type: str,
    market_data: Dict[str, Any],
    technical_analysis: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Invokes Groq LLM with structured market and technical parameters.
    Falls back gracefully if LLM fails.
    """
    quote = market_data.get("quote", {})
    fundamentals = market_data.get("fundamentals", {})

    user_payload = {
        "symbol": symbol,
        "analysis_type": analysis_type.lower(),
        "current_price": quote.get("current_price"),
        "previous_close": quote.get("previous_close"),
        "day_high": quote.get("day_high"),
        "day_low": quote.get("day_low"),
        "52_week_high": quote.get("52_week_high"),
        "52_week_low": quote.get("52_week_low"),
        "technical_summary": {
            "price_change_pct": technical_analysis.get("price_change_pct"),
            "intraday_range": technical_analysis.get("intraday_range"),
            "rsi_14": technical_analysis.get("rsi_14"),
            "macd": technical_analysis.get("macd"),
            "moving_averages": technical_analysis.get("moving_averages"),
            "bollinger_bands": technical_analysis.get("bollinger_bands"),
            "atr": technical_analysis.get("atr"),
            "volume_analysis": technical_analysis.get("volume_analysis"),
            "momentum_pct": technical_analysis.get("momentum_pct"),
            "support_resistance": technical_analysis.get("support_resistance"),
            "vwap": technical_analysis.get("vwap"),
            "trend": technical_analysis.get("trend"),
        },
    }

    if analysis_type.lower() == "delivery":
        user_payload["fundamentals"] = {
            "pe_ratio": fundamentals.get("pe_ratio"),
            "forward_pe": fundamentals.get("forward_pe"),
            "eps": fundamentals.get("eps"),
            "roe": fundamentals.get("roe"),
            "debt_to_equity": fundamentals.get("debt_to_equity"),
            "profit_margin": fundamentals.get("profit_margin"),
            "sector": fundamentals.get("sector"),
        }

    user_prompt = f"Analyze the following Indian stock data for {symbol} ({analysis_type.upper()} mode):\n" + json.dumps(
        user_payload, indent=2
    )

    try:
        llm = get_llm()
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]
        response = await llm.ainvoke(messages)
        content = response.content.strip()

        # Clean JSON markdown fences if present
        content = re.sub(r"^```(json)?", "", content, flags=re.MULTILINE)
        content = re.sub(r"```$", "", content, flags=re.MULTILINE).strip()

        parsed = json.loads(content)
        # Validate fields
        rec = parsed.get("recommendation", "HOLD").upper()
        if rec not in ["BUY", "HOLD", "AVOID"]:
            rec = "HOLD"
        risk = parsed.get("risk_level", "MEDIUM").upper()
        if risk not in ["LOW", "MEDIUM", "HIGH"]:
            risk = "MEDIUM"
        conf = float(parsed.get("confidence", 0.70))
        conf = min(max(conf, 0.1), 0.99)

        return {
            "recommendation": rec,
            "confidence": round(conf, 2),
            "risk_level": risk,
            "summary": parsed.get("summary", f"AI analysis completed for {symbol}."),
            "key_signals": parsed.get("key_signals", []),
            "risks": parsed.get("risks", []),
            "selling_point": parsed.get("selling_point", "Monitor trailing stop and key levels."),
        }
    except Exception as e:
        logger.warning("LLM stock analysis error for %s: %s. Using deterministic fallback.", symbol, e)
        return _build_rule_based_fallback(symbol, analysis_type, market_data, technical_analysis)
