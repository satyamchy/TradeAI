"""Simulated cash and positions for paper mode.

Quantity is signed: positive is a long, negative is a short. Opening either
side reserves last-price times shares from the cash balance, so a short does
not increase the cash that can be spent on the next order. Closing returns
that reserve plus the realized profit or loss.

This file is never sent to Dhan.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


class PaperLedgerError(Exception):
    """A paper fill was rejected."""


class PaperLedger:
    """JSON ledger. Mutations do not await, so they stay atomic on one event loop."""

    def __init__(self, path: str, starting_balance_inr: float):
        self.path = path
        self.starting_balance_inr = float(starting_balance_inr)
        self._state = self._load()

    def available_balance_inr(self) -> float:
        """Cash that is not reserved for an open paper position, in INR."""
        return float(self._state["balance_inr"])

    def open_positions(self) -> list[dict]:
        """Open paper positions. Quantity is signed shares."""
        rows = []
        for key, position in self._state["positions"].items():
            symbol, _, product = key.partition("#")
            if not product:
                symbol = key
                product = position.get("product_type", "INTRADAY")
            rows.append(
                {
                    "symbol": symbol,
                    "security_id": position["security_id"],
                    "quantity": int(position["quantity"]),
                    "average_price": float(position["average_price"]),
                    "last_price": float(position["last_price"]),
                    "realized_pnl_inr": 0.0,
                    "product_type": product,
                }
            )
        return rows

    def orders(self) -> list[dict]:
        """Paper fills, oldest first. Market fills are immediate, so none are working."""
        return list(self._state["orders"])

    def realized_pnl_today_inr(self) -> float:
        """Sum of paper profits booked today in IST, in INR. Losses are negative."""
        return float(self._state["realized_pnl_by_date"].get(_today_ist(), 0.0))

    def set_last_price(self, symbol: str, last_price: float) -> None:
        """Store the latest mark, in INR, without changing cash or quantity."""
        position = self._state["positions"].get(symbol)
        if position is None or last_price <= 0:
            return
        position["last_price"] = float(last_price)
        self._save()

    def fill_intraday_order(
        self,
        symbol: str,
        security_id: str,
        side: str,
        quantity: int,
        price: float,
        product_type: str = "INTRADAY",
    ) -> dict:
        """Fill a market order immediately at `price` INR per share.

        `quantity` is a positive share count. BUY increases the signed
        position; SELL decreases it.
        """
        if side not in {"BUY", "SELL"}:
            raise PaperLedgerError("side must be BUY or SELL")
        if quantity <= 0:
            raise PaperLedgerError("quantity must be greater than 0")
        if price <= 0:
            raise PaperLedgerError("price must be greater than 0")

        signed_quantity = quantity if side == "BUY" else -quantity
        key = symbol if product_type == "INTRADAY" else f"{symbol}#{product_type}"
        self._apply_fill(key, security_id, signed_quantity, float(price), product_type)
        order = {
            "order_id": f"paper-{self._state['next_order_id']}",
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": float(price),
            "status": "FILLED",
            "product_type": product_type,
            "broker": "paper",
        }
        self._state["next_order_id"] += 1
        self._state["orders"].append(order)
        self._state["orders"] = self._state["orders"][-100:]
        self._save()
        return order

    def cancel_order(self, order_id: str) -> dict:
        """Paper market orders fill immediately, so a cancel finds nothing working."""
        return {
            "order_id": order_id,
            "broker": "paper",
            "status": "REJECTED",
            "reason": "Paper market orders fill immediately and cannot be cancelled.",
        }

    def _apply_fill(self, symbol: str, security_id: str, signed_quantity: int, price: float, product_type: str = "INTRADAY") -> None:
        position = self._state["positions"].get(symbol)
        quantity = int(position["quantity"]) if position else 0
        average = float(position["average_price"]) if position else 0.0

        same_side = quantity == 0 or (quantity > 0 and signed_quantity > 0) or (quantity < 0 and signed_quantity < 0)
        if same_side:
            self._reserve(abs(signed_quantity) * price)
            added = abs(signed_quantity)
            total = abs(quantity) + added
            new_average = ((abs(quantity) * average) + (added * price)) / total
            self._state["positions"][symbol] = {
                "security_id": security_id,
                "quantity": quantity + signed_quantity,
                "average_price": new_average,
                "last_price": price,
                "product_type": product_type,
            }
            return

        closing = min(abs(quantity), abs(signed_quantity))
        new_quantity = quantity + signed_quantity
        if (quantity > 0 and new_quantity < 0) or (quantity < 0 and new_quantity > 0):
            raise PaperLedgerError("order would flip the position; close it first")

        if quantity > 0:
            pnl = (price - average) * closing
        else:
            # A short profits when the cover price is below the sale price.
            pnl = (average - price) * closing
        self._state["balance_inr"] += average * closing + pnl
        self._add_realized(pnl)

        if new_quantity == 0:
            del self._state["positions"][symbol]
            return
        position["quantity"] = new_quantity
        position["last_price"] = price

    def _reserve(self, amount_inr: float) -> None:
        if amount_inr > self._state["balance_inr"] + 1e-6:
            raise PaperLedgerError("Insufficient paper balance")
        self._state["balance_inr"] -= amount_inr

    def _add_realized(self, pnl_inr: float) -> None:
        day = _today_ist()
        booked = self._state["realized_pnl_by_date"]
        booked[day] = float(booked.get(day, 0.0)) + pnl_inr

    def _load(self) -> dict:
        if not os.path.exists(self.path):
            return self._empty()
        with open(self.path, encoding="utf-8") as handle:
            state = json.load(handle)
        state.setdefault("positions", {})
        state.setdefault("orders", [])
        state.setdefault("realized_pnl_by_date", {})
        state.setdefault("next_order_id", 1)
        state.setdefault("balance_inr", self.starting_balance_inr)
        return state

    def _empty(self) -> dict:
        return {
            "balance_inr": self.starting_balance_inr,
            "positions": {},
            "orders": [],
            "realized_pnl_by_date": {},
            "next_order_id": 1,
        }

    def _save(self) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(self._state, handle, indent=2)


def _today_ist() -> str:
    return datetime.now(IST).date().isoformat()
