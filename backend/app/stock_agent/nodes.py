# app/agents/stock_agent/nodes.py
from backend.app.stock_agent.state import TradeAgentState, ChecklistResult
from app.services.llm_ticker_resolver import resolve_ticker_via_llm, TickerResolutionError
from app.services.order_execution_service import execute_recommendation


async def resolve_ticker_node(state: TradeAgentState) -> dict:
    try:
        ticker, market_data = await resolve_ticker_via_llm(state["query"])
        return {"ticker": ticker, "market_data": market_data}
    except TickerResolutionError as e:
        return {"error": str(e)}


async def technical_checklist_node(state: TradeAgentState) -> dict:
    """Trend, momentum, volume vs average — pure calculation, no LLM needed here."""
    history = state["market_data"]["history"]
    closes = [c["close"] for c in history if c["close"]]
    if len(closes) < 10:
        result = ChecklistResult(name="technical", passed=False, score=0,
                                  reasoning="Insufficient history", data_used={})
        return {"checklist_results": [result]}

    sma_5 = sum(closes[-5:]) / 5
    sma_10 = sum(closes[-10:]) / 10
    trend_up = sma_5 > sma_10
    momentum_pct = ((closes[-1] - closes[-5]) / closes[-5]) * 100

    score = 6 if trend_up else 3
    score += min(max(momentum_pct, -2), 2)

    result = ChecklistResult(
        name="technical", passed=trend_up and momentum_pct > 0, score=round(score, 1),
        reasoning=f"5-day SMA {'above' if trend_up else 'below'} 10-day SMA; 5-day momentum {momentum_pct:.2f}%",
        data_used={"sma_5": sma_5, "sma_10": sma_10, "momentum_pct": momentum_pct},
    )
    return {"checklist_results": [result]}


async def fundamental_checklist_node(state: TradeAgentState) -> dict:
    """PE, margins, debt — deterministic thresholds, not LLM judgment."""
    f = state["market_data"]["fundamentals"]
    pe = f.get("pe_ratio")
    margin = f.get("profit_margin")
    debt_eq = f.get("debt_to_equity")

    score, reasons = 5.0, []
    if pe is not None:
        if pe < 25: score += 1.5; reasons.append(f"PE {pe} is reasonable")
        elif pe > 60: score -= 1.5; reasons.append(f"PE {pe} is stretched")
    if margin is not None and margin > 10:
        score += 1.5; reasons.append(f"Profit margin {margin:.1f}% is healthy")
    if debt_eq is not None and debt_eq > 100:
        score -= 1.5; reasons.append(f"Debt/equity {debt_eq} is elevated")

    result = ChecklistResult(
        name="fundamental", passed=score >= 5.5, score=round(min(max(score, 0), 10), 1),
        reasoning="; ".join(reasons) or "Insufficient fundamental data",
        data_used={"pe_ratio": pe, "profit_margin": margin, "debt_to_equity": debt_eq},
    )
    return {"checklist_results": [result]}


async def risk_checklist_node(state: TradeAgentState) -> dict:
    """Volatility / liquidity — should this be tradeable at all, independent of direction."""
    history = state["market_data"]["history"]
    volumes = [c["volume"] for c in history[-10:] if c["volume"]]
    avg_volume = sum(volumes) / len(volumes) if volumes else 0
    highs = [c["high"] for c in history[-10:] if c["high"]]
    lows = [c["low"] for c in history[-10:] if c["low"]]
    avg_range_pct = sum((h - l) / l * 100 for h, l in zip(highs, lows) if l) / len(highs) if highs else 0

    liquid = avg_volume > 100_000
    stable_enough = avg_range_pct < 5

    result = ChecklistResult(
        name="risk", passed=liquid and stable_enough,
        score=round((5 if liquid else 2) + (5 if stable_enough else 1), 1),
        reasoning=f"Avg volume {avg_volume:,.0f} ({'liquid' if liquid else 'thin'}), "
                  f"avg daily range {avg_range_pct:.2f}% ({'stable' if stable_enough else 'volatile'})",
        data_used={"avg_volume": avg_volume, "avg_range_pct": avg_range_pct},
    )
    return {"checklist_results": [result]}


async def sentiment_checklist_node(state: TradeAgentState) -> dict:
    """This one genuinely needs the LLM — qualitative read on fundamentals + recent action."""
    from app.services.llm_stock_analysis import analyze_stock_data
    analysis_text = await analyze_stock_data(state["ticker"], state["market_data"])

    # cheap heuristic; swap for a structured LLM call returning a score directly if you want precision
    positive_words = ["growth", "strong", "positive", "outperform", "healthy"]
    negative_words = ["decline", "weak", "concern", "risk", "volatile"]
    pos = sum(w in analysis_text.lower() for w in positive_words)
    neg = sum(w in analysis_text.lower() for w in negative_words)
    score = 5 + pos - neg

    result = ChecklistResult(
        name="sentiment", passed=score >= 5, score=round(min(max(score, 0), 10), 1),
        reasoning=analysis_text, data_used={},
    )
    return {"checklist_results": [result]}


async def aggregate_checklist_node(state: TradeAgentState) -> dict:
    results = state["checklist_results"]
    weights = {"technical": 0.3, "fundamental": 0.3, "risk": 0.25, "sentiment": 0.15}
    weighted = sum(r["score"] * weights.get(r["name"], 0.1) for r in results)
    return {"aggregate_score": round(weighted, 2)}


async def generate_recommendation_node(state: TradeAgentState) -> dict:
    """Combine checklist into an actionable recommendation — deterministic rules,
    not another free-form LLM guess, since the checklist already did the judgment work."""
    score = state["aggregate_score"]
    quote = state["market_data"]["quote"]
    price = quote["current_price"]
    risk_result = next(r for r in state["checklist_results"] if r["name"] == "risk")

    if score >= 7 and risk_result["passed"]:
        action, trade_type = "BUY", "DELIVERY" if score >= 8 else "INTRADAY"
        entry_cap = round(price * 1.005, 2)
        stop_loss = round(price * 0.97, 2)
        target = round(price * 1.05, 2)
    elif score >= 5.5:
        action, trade_type, entry_cap, stop_loss, target = "WATCH", "NONE", None, None, None
    else:
        action, trade_type, entry_cap, stop_loss, target = "AVOID", "NONE", None, None, None

    rec = {
        "action": action, "trade_type": trade_type,
        "entry_price_cap": entry_cap, "stop_loss": stop_loss, "target_price": target,
        "aggregate_score": score,
        "buy_flag": action == "BUY",
        "checklist_summary": [{"name": r["name"], "score": r["score"], "passed": r["passed"]} for r in state["checklist_results"]],
    }
    return {"recommendation": rec}


async def execute_order_node(state: TradeAgentState) -> dict:
    rec = state.get("modified_recommendation") or state["recommendation"]
    if state["human_decision"] == "rejected":
        return {"execution_result": {"attempted": False, "executed": False, "reason": "Rejected by human reviewer"}}

    result = await execute_recommendation(
        instrument_security_id=state["security_id"],
        exchange="NSE",
        recommendation=rec,
        quantity=1,  # or pull from request
        symbol=state["ticker"],
    )
    return {"execution_result": result}