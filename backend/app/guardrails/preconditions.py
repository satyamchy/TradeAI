"""
Precondition checks for the trade *recommendation* agent
(app/agents/trade_recommendation_agent.py).

These are pure functions — no DB or network calls — so the agent/controller
fetches the numbers once (margin, existing positions) and passes them in.
They only inform the BUY/DO_NOT_BUY recommendation; they never place or
block an actual order. The real enforcement gate for orders is
app.guardrails.trading_guardrails.validate_trade_execution(), called by
app.services.dhan_service.place_order() no matter what triggers the order.
"""

from typing import List


def check_preconditions(
    available_margin: float,
    order_value: float,
    max_order_value_inr: float,
    has_open_position: bool,
) -> List[str]:
    """Returns a list of human-readable blocking reasons. Empty list means
    nothing here would stop a BUY — the agent still makes the final call
    using market/technical context too."""
    reasons = []

    if has_open_position:
        reasons.append("An open position already exists for this symbol — avoid doubling up automatically.")

    if order_value > available_margin:
        reasons.append(
            f"Estimated order value (₹{order_value:,.2f}) exceeds available Dhan account margin (₹{available_margin:,.2f})."
        )

    if order_value > max_order_value_inr:
        reasons.append(
            f"Estimated order value (₹{order_value:,.2f}) exceeds the configured max order value guardrail (₹{max_order_value_inr:,.2f})."
        )

    return reasons
