"""
Scheduling — gates the harness's main tick loop to market hours, and drives
the periodic background watchdog cycle (stop-loss/target checks on
already-open positions, from app.services.watchdog_service) on its own
cadence, independent of the per-tick strategy loop.
"""

import asyncio
from typing import Optional

from app.config import settings
from app.services.market_data_service import get_indian_market_status
from app.services.watchdog_service import evaluate_active_positions
from app.utils.logger import get_agent_logger, get_logger

logger = get_logger(__name__)
log = get_agent_logger("WatchdogScheduler")


def is_market_open() -> bool:
    """Thin wrapper around the existing market-hours helper — kept as its
    own function so callers/tests don't need to know the underlying shape
    of get_indian_market_status()'s response."""
    return bool(get_indian_market_status().get("is_open"))


class WatchdogScheduler:
    """
    Runs evaluate_active_positions() every `interval_seconds`, independent
    of the harness's per-tick strategy loop (that loop runs every few
    seconds for entries; the watchdog runs every few minutes for exits on
    positions already opened).
    """

    def __init__(self, interval_seconds: Optional[int] = None):
        self.interval_seconds = interval_seconds or settings.harness_watchdog_interval_seconds
        self._task: Optional[asyncio.Task] = None
        self._stop_flag = asyncio.Event()

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_flag.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info(f"WatchdogScheduler started (every {self.interval_seconds}s).")

    async def stop(self) -> None:
        self._stop_flag.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=self.interval_seconds + 5)
            except asyncio.TimeoutError:
                logger.warning("WatchdogScheduler did not stop within timeout; abandoning task.")

    async def _loop(self) -> None:
        while not self._stop_flag.is_set():
            try:
                if is_market_open():
                    await evaluate_active_positions()
            except Exception as exc:
                # Same isolation principle as the strategy loop: a bad
                # watchdog cycle logs and waits for the next one, it never
                # kills the scheduler.
                await log(f"Watchdog cycle failed: {exc}", status="ERROR")

            try:
                await asyncio.wait_for(self._stop_flag.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                pass
