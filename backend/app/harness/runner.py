"""
The trading harness.

This is the layer that turns "several independent strategies + one broker
connection" into a single running system — the thing referenced throughout
this README as the "backend harness". Its five responsibilities map
directly onto the definition:

  1. Main loop             -> _tick_loop() / _run_one_cycle()
  2. Broker connection     -> DhanFeedManager  (connection_manager.py)
  3. Strategy coordination -> StrategyCoordinator (strategy_coordinator.py)
  4. Scheduling            -> is_market_open() + WatchdogScheduler (scheduler.py)
  5. Centralized logging / error isolation -> _run_strategy_safely() below,
     plus every step logging through app.utils.logger's get_agent_logger
     so failures show up in both the console/log file and the event_logs
     table without each strategy needing its own logging code.

Nothing here is broker-specific business logic (that's in dhan_service.py)
and nothing here is strategy-specific (that's in individual BaseStrategy
subclasses) — this file only wires the pieces together and keeps them
running.
"""

import asyncio
from typing import Optional, Set

from dhanhq import MarketFeed

from app.config import settings
from app.harness.base_strategy import BaseStrategy, OrderIntent
from app.harness.connection_manager import DhanFeedManager
from app.harness.scheduler import is_market_open, WatchdogScheduler
from app.harness.strategy_coordinator import StrategyCoordinator
from app.services import dhan_service
from app.integrations.dhan.client import is_dhan_configured, get_dhan_context
from app.utils.logger import get_agent_logger, get_logger

logger = get_logger(__name__)
log = get_agent_logger("TradingHarness")


class TradingHarness:
    def __init__(self):
        self.coordinator = StrategyCoordinator()
        self.watchdog = WatchdogScheduler()
        self.feed: Optional[DhanFeedManager] = None

        self._open_positions: Set[str] = set()
        self._main_task: Optional[asyncio.Task] = None
        self._stop_flag = asyncio.Event()
        self._running = False
        self._last_error: Optional[str] = None
        self._tick_count = 0

    # ── Public control surface — used by app/api/harness_routes.py ──────

    def register_strategy(self, strategy: BaseStrategy) -> None:
        """Safe to call before or after start(): if the feed is already
        running, the new symbol is subscribed onto the live connection
        immediately instead of requiring a restart."""
        self.coordinator.register(strategy)
        if self.feed:
            self.feed.subscribe(strategy.security_id)

    def unregister_strategy(self, name: str) -> None:
        self.coordinator.unregister(name)

    def status(self) -> dict:
        """Everything you need to debug the harness from one endpoint —
        see GET /v1/harness/status."""
        return {
            "running": self._running,
            "dhan_configured": is_dhan_configured(),
            "feed_connected": self.feed.is_connected if self.feed else False,
            "feed_last_error": self.feed.last_error if self.feed else None,
            "market_open": is_market_open(),
            "strategies": self.coordinator.list_strategies(),
            "open_positions": sorted(self._open_positions),
            "tick_count": self._tick_count,
            "last_error": self._last_error,
        }

    async def start(self) -> None:
        if self._running:
            await log("start() called but harness is already running.", status="WARNING")
            return

        if not is_dhan_configured():
            await log("Cannot start: DhanHQ credentials not configured.", status="ERROR")
            raise RuntimeError("DhanHQ credentials not configured.")

        instruments = [
            (MarketFeed.NSE, s.security_id, MarketFeed.Ticker)
            for s in self.coordinator.strategies
        ]
        if instruments:
            self.feed = DhanFeedManager(get_dhan_context(), instruments)
            self.feed.start()
        else:
            await log("Starting with zero registered strategies — no feed subscriptions yet.", status="WARNING")

        self.watchdog.start()
        self._stop_flag.clear()
        self._running = True
        self._main_task = asyncio.create_task(self._tick_loop())
        await log("Trading harness started.", status="SUCCESS")

    async def stop(self) -> None:
        self._stop_flag.set()
        self._running = False

        if self.feed:
            self.feed.stop()

        await self.watchdog.stop()

        if self._main_task:
            try:
                await asyncio.wait_for(self._main_task, timeout=15)
            except asyncio.TimeoutError:
                logger.warning("Main tick loop did not exit within timeout.")

        await log("Trading harness stopped.", status="INFO")

    # ── Main loop ─────────────────────────────────────────────────────

    async def _tick_loop(self) -> None:
        interval = settings.harness_tick_interval_seconds

        while not self._stop_flag.is_set():
            try:
                if is_market_open():
                    await self._run_one_cycle()
            except Exception as exc:
                # Loop-level safety net. Individual strategy errors are
                # already isolated inside _run_strategy_safely(); this
                # catches anything unexpected in the plumbing around it
                # (e.g. the margin-check call itself failing) so the loop
                # itself is never the thing that dies.
                self._last_error = str(exc)
                await log(f"Tick loop error: {exc}", status="ERROR")

            try:
                await asyncio.wait_for(self._stop_flag.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

        await log("Tick loop exited.", status="INFO")

    async def _run_one_cycle(self) -> None:
        self._tick_count += 1

        margin = await dhan_service.get_margin_snapshot()
        context = {
            "available_margin": margin.get("available_margin", 0.0),
            "open_positions": self._open_positions,
            "market_open": True,
        }

        for strategy in self.coordinator.strategies:
            await self._run_strategy_safely(strategy, context)

    async def _run_strategy_safely(self, strategy: BaseStrategy, context: dict) -> None:
        """
        Isolates one strategy's failure from every other strategy and from
        the loop itself. A bug or unhandled exception in one trading logic
        must never stop the others from running this cycle or any future
        cycle — this is the "one broken strategy doesn't crash the whole
        bot" half of the harness definition.
        """
        try:
            price = self.feed.get_last_price(strategy.security_id) if self.feed else None
            if price is None:
                return  # no tick for this symbol yet this cycle — nothing to evaluate

            intent = await strategy.evaluate(price, context)
            if intent is None:
                return

            await self._execute_intent(strategy, intent, price)

        except Exception as exc:
            await log(
                f"Strategy '{strategy.name}' raised an exception: {exc}",
                ticker=strategy.symbol,
                status="ERROR",
            )

    async def _execute_intent(self, strategy: BaseStrategy, intent: OrderIntent, price: float) -> None:
        """
        Every order from every strategy funnels through here, guarded by
        the per-symbol lock — this is the "two strategies don't step on
        each other" half of the harness definition.
        """
        lock = self.coordinator.lock_for(strategy.symbol)

        async with lock:
            # Re-check inside the lock: another strategy on the same
            # symbol may have filled this exact intent while we waited.
            if intent.trade_type == "BUY" and strategy.symbol in self._open_positions:
                await log(
                    f"Skipped duplicate BUY for {strategy.symbol}: position already open.",
                    ticker=strategy.symbol,
                    status="WARNING",
                )
                return

            try:
                result = await dhan_service.place_order(
                    symbol=strategy.symbol,
                    trade_type=intent.trade_type,
                    quantity=intent.quantity,
                    price=price,
                    product_type=intent.product_type,
                    stop_loss=intent.stop_loss,
                    target_price=intent.target_price,
                    notes=f"[{strategy.name}] {intent.reason}",
                )

                if intent.trade_type == "BUY":
                    self._open_positions.add(strategy.symbol)
                else:
                    self._open_positions.discard(strategy.symbol)

                await log(
                    f"Executed {intent.trade_type} for {strategy.symbol} via "
                    f"'{strategy.name}': order_id={result.get('order_id')}",
                    ticker=strategy.symbol,
                    status="SUCCESS",
                )

            except Exception as exc:
                await log(
                    f"Order execution failed for {strategy.symbol} via '{strategy.name}': {exc}",
                    ticker=strategy.symbol,
                    status="ERROR",
                )


# One harness per process, imported by main.py and app/api/harness_routes.py.
harness = TradingHarness()
