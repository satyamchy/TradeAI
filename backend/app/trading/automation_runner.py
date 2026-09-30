"""Market-hours loop for intraday entries and exits.

The production runner has no single account. It visits each trader whose
automation state is entries or exits_only, and that state is stored on the
user. Disable stops new entries. Open intraday positions are still exited
on take-profit, stop-loss, and the 15:15 IST square-off.

A runner built with one gateway is the test path. Its enable flag lives in
memory and a new process starts with entries off.
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime

from app.broker.trading_gateway import TradingGateway
from app.config import settings
from app.trading.intraday_cycle import run_intraday_cycle
from app.trading.nse_session import (
    is_nse_cash_session_open,
    is_past_entry_cutoff,
    is_square_off_time,
    now_ist,
)
from app.trading.risk_limits import RiskLimits
from app.utils.logger import get_logger

logger = get_logger(__name__)

ALLOWED_METHODS = ("intraday_long", "intraday_short")
CYCLE_HISTORY = 50


class AutomationRunner:
    """Owns the enable flag, the in-memory limits, and the recent cycle snapshots."""

    def __init__(self, gateway: TradingGateway | None = None):
        self.gateway = gateway
        self.entries_enabled = False
        self.methods: list[str] = []
        self.limits = limits_from_settings()
        self.cycles: deque[dict] = deque(maxlen=CYCLE_HISTORY)
        self.user_cycles: dict[int, deque] = {}
        self.user_errors: dict[int, str] = {}
        self.last_error: str | None = None
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        """Start the wait loop. Entries stay off until `enable` is called."""
        if self._task and not self._task.done():
            return
        # A new event each start. TestClient gives every test its own loop,
        # and an Event cannot be waited on from a loop it was not created in.
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._loop())
        logger.info("Automation runner started. Entries are disabled.")

    async def stop(self) -> None:
        """Stop the wait loop. Open positions are not flattened here."""
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=self.limits.cycle_interval_seconds + 5)
            except asyncio.TimeoutError:
                logger.warning("Automation runner did not stop before the timeout.")

    def enable(self, methods: list[str]) -> None:
        """Allow new entries for the named methods.

        This does not change paper into live. That switch is TRADING_MODE,
        read when the gateway is created. Live automation is accepted only
        when that value is already `live`. Any other mode except `paper`
        is refused. A restart clears this flag.
        """
        if self.gateway is None:
            raise RuntimeError("This runner has no single gateway. Automation is stored on each user.")
        if self.gateway.mode == "live" and settings.trading_mode.strip().lower() != "live":
            raise ValueError(
                "Live automation is refused until TRADING_MODE=live is set in the environment."
            )
        if self.gateway.mode not in {"paper", "live"}:
            raise ValueError("TRADING_MODE must be paper or live")
        unknown = [method for method in methods if method not in ALLOWED_METHODS]
        if unknown or not methods:
            raise ValueError("methods must include intraday_long, intraday_short, or both")
        self.methods = list(dict.fromkeys(methods))
        self.entries_enabled = True
        self.last_error = None
        logger.info("Entries enabled for %s in %s mode.", self.methods, self.gateway.mode)

    def disable(self) -> None:
        """Stop new entries. The session loop still flattens open positions."""
        self.entries_enabled = False
        logger.info("Entries disabled.")

    def replace_limits(self, updates: dict) -> RiskLimits:
        """Replace the in-memory limits. Unset fields keep their current value."""
        current = self.limits
        updated = RiskLimits(
            max_positions=int(updates.get("max_positions", current.max_positions)),
            capital_per_trade_pct=float(updates.get("capital_per_trade_pct", current.capital_per_trade_pct)),
            cash_reserve_pct=float(updates.get("cash_reserve_pct", current.cash_reserve_pct)),
            take_profit_pct=float(updates.get("take_profit_pct", current.take_profit_pct)),
            stop_loss_pct=float(updates.get("stop_loss_pct", current.stop_loss_pct)),
            max_daily_loss_inr=float(updates.get("max_daily_loss_inr", current.max_daily_loss_inr)),
            screener_limit=int(updates.get("screener_limit", current.screener_limit)),
            cycle_interval_seconds=int(updates.get("cycle_interval_seconds", current.cycle_interval_seconds)),
        )
        _validate_limits(updated)
        self.limits = updated
        return self.limits

    async def run_once(self, now: datetime | None = None) -> dict | None:
        """Run one pass when the session is open and there is work to do.

        Returns None outside the session, and when entries are off and
        nothing is open. That is the closed-market no-op.
        """
        moment = now or now_ist()
        if not is_nse_cash_session_open(moment):
            return None
        if not self.entries_enabled:
            positions = await self.gateway.get_open_positions()
            if not positions:
                return None
        try:
            snapshot = await run_intraday_cycle(
                self.gateway,
                entries_enabled=self.entries_enabled,
                methods=self.methods,
                limits=self.limits,
                now=moment,
            )
        except Exception as exc:
            self.last_error = str(exc)
            logger.error("Intraday cycle failed: %s", exc)
            raise
        self.cycles.append(snapshot)
        return snapshot

    async def square_off_open_positions(self, now: datetime | None = None) -> dict:
        """Close every open intraday position now, including outside the session."""
        snapshot = await run_intraday_cycle(
            self.gateway,
            entries_enabled=False,
            methods=self.methods,
            limits=self.limits,
            now=now or now_ist(),
            force_square_off=True,
        )
        self.cycles.append(snapshot)
        return snapshot

    async def status(self, now: datetime | None = None) -> dict:
        """What the frontend needs to see whether the loop will trade."""
        moment = now or now_ist()
        session_open = is_nse_cash_session_open(moment)
        past_cutoff = is_past_entry_cutoff(moment)
        square_off_due = session_open and is_square_off_time(moment)
        position_count = None
        try:
            position_count = len(await self.gateway.get_open_positions())
        except Exception as exc:
            self.last_error = str(exc)

        if not self.entries_enabled:
            next_action = "managing_exits_only" if position_count else "disabled"
        elif not session_open:
            next_action = "waiting_for_session"
        elif square_off_due:
            next_action = "square_off"
        elif past_cutoff:
            next_action = "managing_exits_only"
        else:
            next_action = "running_entries"

        return {
            "enabled": self.entries_enabled,
            "mode": self.gateway.mode,
            "methods": list(self.methods),
            "market_open": session_open,
            "past_entry_cutoff": past_cutoff,
            "square_off_due": square_off_due,
            "next_action": next_action,
            "last_error": self.last_error,
            "open_position_count": position_count,
            "cycle_count": len(self.cycles),
        }

    def recent_cycles(self) -> list[dict]:
        """Newest snapshots last, capped at 50."""
        return list(self.cycles)

    async def run_enabled_traders(self, now: datetime | None = None) -> None:
        """One pass per trader who turned entries on, or still has exits to manage."""
        import json

        from app import db
        from app.broker.trading_gateway import gateway_for_user

        moment = now or now_ist()
        if not is_nse_cash_session_open(moment):
            return
        for user in db.traders_to_run():
            gateway = gateway_for_user(user)
            methods = json.loads(user["automation_methods"] or "[]")
            entries_on = user["automation_state"] == "entries"
            try:
                snapshot = await run_intraday_cycle(
                    gateway,
                    entries_enabled=entries_on,
                    methods=methods,
                    limits=self.limits,
                    now=moment,
                )
                self.user_cycles.setdefault(user["id"], deque(maxlen=CYCLE_HISTORY)).append(snapshot)
                self.user_errors.pop(user["id"], None)
                if not entries_on:
                    still_open = await gateway.get_open_positions()
                    intraday = [row for row in still_open if row.get("product_type", "INTRADAY") == "INTRADAY"]
                    if not intraday:
                        db.set_automation(user["id"], "off", "[]")
            except Exception as exc:
                self.user_errors[user["id"]] = str(exc)
                logger.error("Intraday cycle failed for user %s: %s", user["id"], exc)

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if self.gateway is None:
                    await self.run_enabled_traders()
                else:
                    await self.run_once()
            except Exception as exc:
                self.last_error = str(exc)
                logger.error("Automation loop failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.limits.cycle_interval_seconds)
            except asyncio.TimeoutError:
                pass


def limits_from_settings() -> RiskLimits:
    """Copy the environment defaults into a limits object the runner can edit."""
    limits = RiskLimits(
        max_positions=settings.max_positions,
        capital_per_trade_pct=settings.capital_per_trade_pct,
        cash_reserve_pct=settings.cash_reserve_pct,
        take_profit_pct=settings.take_profit_pct,
        stop_loss_pct=settings.stop_loss_pct,
        max_daily_loss_inr=settings.max_daily_loss_inr,
        screener_limit=settings.screener_limit,
        cycle_interval_seconds=settings.cycle_interval_seconds,
    )
    _validate_limits(limits)
    return limits


def _validate_limits(limits: RiskLimits) -> None:
    if limits.max_positions < 1:
        raise ValueError("max_positions must be at least 1")
    if not 0 < limits.capital_per_trade_pct <= 1:
        raise ValueError("capital_per_trade_pct must be between 0 and 1")
    if not 0 <= limits.cash_reserve_pct < 1:
        raise ValueError("cash_reserve_pct must be between 0 and 1")
    if limits.take_profit_pct <= 0 or limits.stop_loss_pct <= 0:
        raise ValueError("take_profit_pct and stop_loss_pct must be greater than 0")
    if limits.max_daily_loss_inr <= 0:
        raise ValueError("max_daily_loss_inr must be greater than 0")
    if limits.screener_limit < 1:
        raise ValueError("screener_limit must be at least 1")
    if limits.cycle_interval_seconds < 30:
        raise ValueError("cycle_interval_seconds must be at least 30")


automation_runner = AutomationRunner()
