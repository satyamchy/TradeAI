"""
Base class every trading "logic" (strategy) implements to plug into the
harness.

A strategy does NOT talk to Dhan directly. It only looks at a price tick
plus whatever shared context the harness hands it, and returns an
OrderIntent (or None). The harness (app/harness/runner.py) is the only
thing that actually calls dhan_service.place_order(), which keeps every
order path — no matter which strategy triggered it — going through the
same guardrails, margin check, symbol-lock, and logging.

This is what makes "adding a necessary function" easy: a new trading idea
is a new file with one class and one method (see example_strategies.py),
registered with harness.register_strategy(...). Nothing else in the app
needs to change.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class OrderIntent:
    """What a strategy wants to happen. The harness decides whether it
    actually can (guardrails, margin, existing position) and executes it."""

    trade_type: str  # "BUY" or "SELL"
    quantity: int
    product_type: str = "INTRADAY"
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    reason: str = ""


class BaseStrategy(ABC):
    """
    Subclass this for every new trading logic. Give it a unique `name` and
    the `symbol` / `security_id` it watches; the harness calls `evaluate()`
    once per price tick for that symbol.
    """

    def __init__(self, name: str, symbol: str, security_id: str):
        self.name = name
        self.symbol = symbol
        self.security_id = security_id

    @abstractmethod
    async def evaluate(self, price: float, context: Dict[str, Any]) -> Optional[OrderIntent]:
        """
        Called on every new tick for `self.symbol`.

        `context` currently includes:
          - available_margin: float — from dhan_service.get_margin_snapshot()
          - open_positions: set[str] — symbols the harness currently holds
          - market_open: bool

        Extend this dict in runner.py's _run_one_cycle() as new strategies
        need more shared inputs (e.g. technical indicators), rather than
        having each strategy fetch its own data independently.

        Return an OrderIntent to trade this tick, or None to do nothing.
        Raising an exception here is safe — the harness isolates each
        strategy's errors so one broken strategy never affects the others.
        """
        raise NotImplementedError
