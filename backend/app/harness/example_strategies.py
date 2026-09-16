"""
Reference strategy — shows the plug-in shape new trading logics should
follow. Keep this file around as a template, or delete it once you have
real strategies; the harness treats every BaseStrategy subclass identically.
"""

from typing import Any, Dict, Optional

from app.harness.base_strategy import BaseStrategy, OrderIntent


class ThresholdBuyStrategy(BaseStrategy):
    """
    Toy example: buys a fixed quantity the first time price drops to or
    below `buy_below`, and won't buy again for the same symbol while
    `context["open_positions"]` already shows a position open (the harness
    tracks that, not the strategy).

    Swap this out for your real logic — RSI/MACD/pivot-based signals
    (there's already technical_analysis_service.py in this repo), a model
    prediction, whatever. The only contract the harness cares about is
    `evaluate(price, context) -> OrderIntent | None`.
    """

    def __init__(self, name: str, symbol: str, security_id: str, buy_below: float, quantity: int):
        super().__init__(name, symbol, security_id)
        self.buy_below = buy_below
        self.quantity = quantity

    async def evaluate(self, price: float, context: Dict[str, Any]) -> Optional[OrderIntent]:
        if self.symbol in context.get("open_positions", set()):
            return None

        if price <= self.buy_below:
            return OrderIntent(
                trade_type="BUY",
                quantity=self.quantity,
                product_type="INTRADAY",
                reason=f"{self.name}: price {price} <= threshold {self.buy_below}",
            )

        return None
