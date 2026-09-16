"""
Controllers orchestrate multiple services/agents/guardrails for a single
use case, keeping routes thin (parse request -> call controller -> return)
and keeping any one service from having to know about the others.

Not every route needs one — a route that's a single service call (list
trades, get holdings) stays a direct route -> service call; a controller
here is for flows that genuinely coordinate more than one thing, like
trade_recommendation_controller.py (market data + account context + agent +
guardrails).
"""
