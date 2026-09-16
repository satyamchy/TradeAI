"""
Guardrails — every safety check that gates whether a trade may happen.

- trading_guardrails.py: the master kill-switch, paper/live mode, and the
  order-value / daily-loss limits. This is what dhan_service.place_order()
  checks before any order (paper or live) goes out.
- preconditions.py: read-only checks used by the trade *recommendation*
  agent (app/agents/trade_recommendation_agent.py) to decide whether BUY is
  even a sensible answer — insufficient margin, an already-open position in
  the same symbol, etc. These never place or block an order themselves;
  they only inform the recommendation. Execution is always gated separately
  by trading_guardrails at the point of actually placing the order.
"""
