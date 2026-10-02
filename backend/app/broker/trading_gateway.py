"""Chooses the paper ledger or Dhan for account reads and order placement.

Callers use this object. They do not import `dhanhq`. Paper mode never
asks Dhan for balances, positions, orders, or fills. Security ids and
candles may still come from Dhan when credentials exist; that lookup
lives in `dhan_gateway`.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from app.broker import dhan_gateway
from app.broker.paper_ledger import PaperLedger
from app.config import settings
from app.trading.nifty50 import normalize_symbol


class TradingGateway:
    """One account interface for the cycle and the HTTP routes."""

    def __init__(
        self,
        mode: str | None = None,
        ledger_path: str | None = None,
        starting_balance_inr: float | None = None,
        creds: tuple[str, str] | None = None,
    ):
        self.mode = (mode or settings.trading_mode).strip().lower()
        if self.mode not in {"paper", "live"}:
            raise ValueError("TRADING_MODE must be paper or live")
        self._creds = creds
        self.user_id = None
        self._lock = asyncio.Lock()
        self._cycle_lock = asyncio.Lock()
        self._paper = PaperLedger(
            ledger_path or settings.paper_ledger_path,
            settings.paper_starting_balance_inr if starting_balance_inr is None else starting_balance_inr,
        )

    @asynccontextmanager
    async def exclusive(self):
        """One pass per user. Square-off, the loop, and a manual order take this first."""
        async with self._cycle_lock:
            yield

    def _live_creds(self) -> tuple[str, str]:
        return dhan_gateway.require_user_creds(self._creds)

    async def get_available_balance_inr(self) -> float:
        """Cash available for a new reserve, in INR."""
        async with self._lock:
            if self.mode == "live":
                return await dhan_gateway.get_available_balance_inr(self._live_creds())
            self._paper.reload()
            return self._paper.available_balance_inr()

    async def get_open_positions(self) -> list[dict]:
        """Open positions. Quantity is signed shares. Delivery and intraday are both included."""
        async with self._lock:
            if self.mode == "live":
                return await dhan_gateway.get_account_book(self._live_creds())
            self._paper.reload()
            return self._paper.open_positions()

    async def get_orders(self) -> list[dict]:
        """Orders the active mode can see. Paper returns its own fills."""
        async with self._lock:
            if self.mode == "live":
                return await dhan_gateway.get_orders(self._live_creds())
            self._paper.reload()
            return self._paper.orders()

    async def quote_prices(self, symbols: list[str]) -> dict[str, float]:
        """Dhan last price for each symbol. Omits a name when the quote is missing."""
        if self.mode == "live":
            creds = self._live_creds()
        elif self._creds:
            creds = self._creds
        elif dhan_gateway.is_dhan_configured():
            creds = None
        else:
            return {}
        mapping: dict[str, str] = {}
        for symbol in symbols:
            security_id = await self.resolve_security_id(normalize_symbol(symbol))
            if security_id:
                mapping[normalize_symbol(symbol)] = security_id
        return await dhan_gateway.quote_prices(mapping, creds)

    async def resolve_security_id(self, symbol: str) -> str | None:
        """Dhan security id for an NSE symbol. None when Dhan is not configured or the symbol is missing.

        Paper fills store this id and do not send it to the exchange. A missing
        id skips the symbol. The ledger does not invent one.
        """
        if self.mode == "paper" and not self._creds and not dhan_gateway.is_dhan_configured():
            # Paper fills never leave this process, so the symbol is enough.
            # Live mode still refuses an order when Dhan has no security id.
            return normalize_symbol(symbol)
        creds = self._creds
        if creds is None and not dhan_gateway.is_dhan_configured():
            return None
        return await dhan_gateway.resolve_security_id(normalize_symbol(symbol), creds)

    async def place_intraday_order(
        self,
        symbol: str,
        security_id: str,
        side: str,
        quantity: int,
        price: float,
        product_type: str = "INTRADAY",
    ) -> dict:
        """Place a market order. `product_type` is INTRADAY or DELIVERY.

        `price` is INR per share. Paper fills at that price. Live sends a
        Dhan market order and keeps `price` only as the reference we sized against.
        """
        symbol = normalize_symbol(symbol)
        async with self._lock:
            if self.mode == "live":
                placed = await dhan_gateway.place_market_order(
                    security_id, side, quantity, product_type, self._live_creds(), tag=None
                )
                placed.update({"symbol": symbol, "side": side, "quantity": quantity, "price": price, "product_type": product_type})
                return placed
            return self._paper.fill_intraday_order(
                symbol, security_id, side, quantity, price, product_type=product_type
            )

    async def place_tagged_order(
        self,
        symbol: str,
        security_id: str,
        side: str,
        quantity: int,
        price: float,
        product_type: str,
        tag: str,
    ) -> dict:
        """Place one order under a correlation id that was stored before the call."""
        symbol = normalize_symbol(symbol)
        async with self._lock:
            if self.mode == "live":
                placed = await dhan_gateway.place_market_order(
                    security_id, side, quantity, product_type, self._live_creds(), tag=tag
                )
            else:
                placed = self._paper.fill_intraday_order(
                    symbol, security_id, side, quantity, price, product_type=product_type
                )
            placed.update({"symbol": symbol, "side": side, "quantity": quantity, "price": price, "product_type": product_type})
            return placed

    async def arm_protective_stop(
        self,
        symbol: str,
        security_id: str,
        entry_side: str,
        quantity: int,
        price: float,
        product_type: str,
        stop_loss_pct: float,
    ) -> dict | None:
        """Park a stop-market at Dhan after a live fill. Paper keeps the percent exit in the loop."""
        if self.mode != "live" or quantity <= 0 or price <= 0 or stop_loss_pct <= 0:
            return None
        exit_side = "SELL" if entry_side == "BUY" else "BUY"
        if entry_side == "BUY":
            trigger = price * (1 - stop_loss_pct / 100)
        else:
            trigger = price * (1 + stop_loss_pct / 100)
        async with self._lock:
            placed = await dhan_gateway.place_stop_order(
                security_id, exit_side, quantity, trigger, product_type, self._live_creds()
            )
        from app import db

        if self.user_id is not None:
            db.add_protective_stop(
                self.user_id, normalize_symbol(symbol), product_type, quantity, placed["order_id"], exit_side, trigger
            )
        return placed

    async def cancel_protective_stops(self, symbol: str, product_type: str) -> None:
        """Cancel working broker stops for this symbol before a market exit."""
        if self.user_id is None:
            return
        from app import db

        for row in db.working_stops(self.user_id, normalize_symbol(symbol), product_type):
            order_id = row.get("stop_order_id") or ""
            if self.mode == "live" and order_id:
                try:
                    async with self._lock:
                        await dhan_gateway.cancel_order(order_id, self._live_creds())
                except dhan_gateway.DhanRequestError:
                    pass
            db.finish_stop(row["id"], "cancelled")

    async def cancel_order(self, order_id: str) -> dict:
        """Cancel a working live order. Paper market fills are already done."""
        async with self._lock:
            if self.mode == "live":
                return await dhan_gateway.cancel_order(order_id, self._live_creds())
            return self._paper.cancel_order(order_id)

    async def set_last_price(self, symbol: str, last_price: float, product_type: str = "INTRADAY") -> None:
        """Update the paper mark. Live marks come from Dhan on the next position read."""
        if self.mode == "live":
            return
        async with self._lock:
            self._paper.set_last_price(normalize_symbol(symbol), last_price, product_type)

    async def realized_pnl_today_inr(self) -> float:
        """Realized intraday profit today, in INR. Losses are negative."""
        async with self._lock:
            if self.mode == "live":
                return await dhan_gateway.get_realized_pnl_today_inr(self._live_creds())
            self._paper.reload()
            return self._paper.realized_pnl_today_inr()


_gateway: TradingGateway | None = None
_user_gateways: dict[tuple[int, str, str], TradingGateway] = {}


def _ledger_dir() -> Path:
    raw = Path(settings.paper_ledger_dir)
    if raw.is_absolute():
        return raw
    return Path(__file__).resolve().parents[2] / raw


def gateway_for_user(user: dict) -> TradingGateway:
    """That user's paper ledger, or their own Dhan token when the process is live.

    The same object is reused for a user and ledger path so the locks cover
    the automation loop and the HTTP routes together.
    """
    from app.auth import decrypt_secret

    ledger_path = str(_ledger_dir() / f"{user['id']}.json")
    creds = None
    client_id = decrypt_secret(user.get("dhan_client_id"))
    token = decrypt_secret(user.get("dhan_access_token"))
    if client_id and token:
        creds = (client_id, token)
    key = (int(user["id"]), ledger_path, (settings.trading_mode or "paper").strip().lower())
    gateway = _user_gateways.get(key)
    if gateway is None:
        gateway = TradingGateway(ledger_path=ledger_path, creds=creds)
        gateway.user_id = int(user["id"])
        _user_gateways[key] = gateway
    else:
        gateway._creds = creds
        gateway.user_id = int(user["id"])
    return gateway


def get_trading_gateway() -> TradingGateway:
    """Process-wide gateway. Mode is fixed from the environment at first use."""
    global _gateway
    if _gateway is None:
        _gateway = TradingGateway()
    return _gateway
