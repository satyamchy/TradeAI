# Decision & Risk Engine (Module 3)

Owns provider-neutral strategies, position sizing, risk checks, and approved order-intent generation. Only this module may create an `ApprovedOrderIntent`. It must not import TradingAgents, LangChain/LangGraph providers, or broker order services.

The public protocol and shared DTOs are structural in Phase 1. Existing checks remain in `app/trading/risk_limits.py` until isolated Module 3 implementation and regression tests justify a gradual move.
