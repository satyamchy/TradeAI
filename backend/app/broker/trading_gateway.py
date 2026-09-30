"""Chooses the paper ledger or Dhan for account reads and order placement.

Callers use this object. They do not import `dhanhq`. Paper mode never
asks Dhan for balances, positions, orders, or fills. Security ids and
candles may still come from Dhan when credentials exist; that lookup
lives in `dhan_gateway`.
"""

from __future__ import annotations

import asyncio

from app.broker import dhan_gateway
from app.broker.paper_ledger import PaperLedger
from app.config import settings
from app.trading.nifty50 import normalize_symbol


class TradingGateway:
    """One account interface for the cycle and the HTTP routes."""

    def __init__(self, mode: str | None = None, ledger_path: str | None = None, starting_balance_inr: float | None = None):
        self.mode = (mode or settings.trading_mode).strip().lower()
        if self.mode not in {"paper", "live"}:
            raise ValueError("TRADING_MODE must be paper or live")
        self._lock = asyncio.Lock()
        self._paper = PaperLedger(
            ledger_path or settings.paper_ledger_path,
            settings.paper_starting_balance_inr if starting_balance_inr is None else starting_balance_inr,
        )

    async def get_available_balance_inr(self) -> float:
        """Cash available for a new reserve, in INR."""
        async with self._lock:
            if self.mode == "live":
                return await dhan_gateway.get_available_balance_inr()
            return self._paper.available_balance_inr()

    async def get_open_positions(self) -> list[dict]:
        """Open intraday positions. Quantity is signed shares."""
        async with self._lock:
            if self.mode == "live":
                return await dhan_gateway.get_intraday_positions()
            return self._paper.open_positions()

    async def get_orders(self) -> list[dict]:
        """Orders the active mode can see. Paper returns its own fills."""
        async with self._lock:
            if self.mode == "live":
                return await dhan_gateway.get_orders()
            return self._paper.orders()

    async def resolve_security_id(self, symbol: str) -> str | None:
        """Dhan security id for an NSE symbol. None when Dhan is not configured or the symbol is missing.

        Paper fills store this id and do not send it to the exchange. A missing
        id skips the symbol. The ledger does not invent one.
        """
        if not dhan_gateway.is_dhan_configured():
            return None
        return await dhan_gateway.resolve_security_id(normalize_symbol(symbol))

    async def place_intraday_order(
        self,
        symbol: str,
        security_id: str,
        side: str,
        quantity: int,
        price: float,
    ) -> dict:
        """Place an intraday market order.

        `price` is INR per share. Paper fills at that price. Live sends a
        Dhan market order and keeps `price` only as the reference we sized against.
        """
        symbol = normalize_symbol(symbol)
        async with self._lock:
            if self.mode == "live":
                placed = await dhan_gateway.place_intraday_market_order(security_id, side, quantity)
                placed.update({"symbol": symbol, "side": side, "quantity": quantity, "price": price})
                return placed
            return self._paper.fill_intraday_order(symbol, security_id, side, quantity, price)

    async def cancel_order(self, order_id: str) -> dict:
        """Cancel a working live order. Paper market fills are already done."""
        async with self._lock:
            if self.mode == "live":
                return await dhan_gateway.cancel_order(order_id)
            return self._paper.cancel_order(order_id)

    async def set_last_price(self, symbol: str, last_price: float) -> None:
        """Update the paper mark. Live marks come from Dhan on the next position read."""
        if self.mode == "live":
            return
        async with self._lock:
            self._paper.set_last_price(normalize_symbol(symbol), last_price)

    async def realized_pnl_today_inr(self) -> float:
        """Realized intraday profit today, in INR. Losses are negative."""
        async with self._lock:
            if self.mode == "live":
                return await dhan_gateway.get_realized_pnl_today_inr()
            return self._paper.realized_pnl_today_inr()


_gateway: TradingGateway | None = None


def get_trading_gateway() -> TradingGateway:
    """Process-wide gateway. Mode is fixed from the environment at first use."""
    global _gateway
    if _gateway is None:
        _gateway = TradingGateway()
    return _gateway
