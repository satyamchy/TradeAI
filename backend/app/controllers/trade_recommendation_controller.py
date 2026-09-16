"""
Trade recommendation controller.

Orchestrates the full flow the architecture calls for:

    stock -> market/technical analysis -> Dhan account balance/holdings context
        -> agent loop (app.agents.trade_recommendation_agent)
        -> precondition & risk checks (app.guardrails.preconditions)
        -> final BUY / DO_NOT_BUY recommendation

This is the one place that layer boundary is enforced: it calls the agent
for a reasoned decision, then can only ever downgrade BUY -> DO_NOT_BUY based
on the deterministic precondition checks — it never upgrades DO_NOT_BUY to
BUY. It builds the account context itself (available margin, whether a
position is already open) and only ever passes those two numbers to the
agent — never a Dhan token or credential.

This function is read-only end to end. It does not call
app.services.dhan_service.place_order — turning a recommendation into an
actual order is a separate, explicit action through POST /trading/orders,
which goes through its own guardrail check regardless of what recommended it.
"""

from typing import Any, Dict

from app.services.company_resolver import resolve_ticker_symbol
from app.services.market_data_service import fetch_stock_market_data
from app.services.technical_analysis_service import run_technical_analysis
from app.services.dhan_service import get_margin_snapshot, get_holdings
from app.guardrails.trading_guardrails import get_guardrail_settings
from app.guardrails.preconditions import check_preconditions
from app.agents.trade_recommendation_agent import generate_recommendation


async def _has_open_position(ticker: str) -> bool:
    """Checks Dhan holdings for an existing position in this symbol. Best-effort:
    if holdings can't be fetched (e.g. Dhan not configured), assumes no open
    position rather than blocking every recommendation on an unrelated outage."""
    try:
        holdings_res = await get_holdings()
        target = ticker.upper().replace(".NS", "").replace(".BO", "")
        for h in holdings_res.get("holdings", []):
            if h.get("symbol", "").upper().replace(".NS", "") == target:
                return True
    except Exception:
        pass
    return False


async def get_trade_recommendation(ticker: str, quantity: int = 1, product_type: str = "INTRADAY") -> Dict[str, Any]:
    canonical = resolve_ticker_symbol(ticker)

    market_data = await fetch_stock_market_data(canonical)
    technical_analysis = run_technical_analysis(market_data, analysis_type="intraday")
    quote = market_data.get("quote", {})
    current_price = quote.get("current_price") or 0.0

    margin_snapshot = await get_margin_snapshot()
    has_open_position = await _has_open_position(canonical)
    account_context = {
        "available_margin": margin_snapshot.get("available_margin", 0.0),
        "has_open_position": has_open_position,
    }

    technical_summary = {
        "current_price": current_price,
        "trend": technical_analysis.get("trend"),
        "rsi_14": technical_analysis.get("rsi_14"),
        "macd": technical_analysis.get("macd"),
        "support_resistance": technical_analysis.get("support_resistance"),
        "atr": technical_analysis.get("atr"),
        "volume_analysis": technical_analysis.get("volume_analysis"),
    }

    agent_result = await generate_recommendation(canonical, technical_summary, account_context)

    guardrails = await get_guardrail_settings()
    order_value = current_price * quantity
    blocking_reasons = check_preconditions(
        available_margin=account_context["available_margin"],
        order_value=order_value,
        max_order_value_inr=guardrails["max_order_value_inr"],
        has_open_position=has_open_position,
    )

    final_decision = agent_result["decision"]
    reasoning = agent_result["reasoning"]
    if blocking_reasons and final_decision == "BUY":
        final_decision = "DO_NOT_BUY"
        reasoning = (
            f"{reasoning} Overridden to DO_NOT_BUY by precondition checks: {'; '.join(blocking_reasons)}"
        ).strip()

    return {
        "ticker": canonical,
        "decision": final_decision,
        "confidence": agent_result["confidence"],
        "reasoning": reasoning,
        "risk_level": agent_result["risk_level"],
        "blocking_reasons": blocking_reasons,
        "key_signals": agent_result["key_signals"],
    }
