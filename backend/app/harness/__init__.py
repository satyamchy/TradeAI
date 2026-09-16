"""
Backend harness package — see runner.py for the full explanation.

Import `harness` from here to register strategies or check status from
anywhere in the app:

    from app.harness import harness, BaseStrategy, OrderIntent

    harness.register_strategy(MyStrategy(...))
"""

from app.harness.runner import harness, TradingHarness
from app.harness.base_strategy import BaseStrategy, OrderIntent

__all__ = ["harness", "TradingHarness", "BaseStrategy", "OrderIntent"]
