"""
Broker connection lifecycle — owns the DhanHQ live market-feed websocket.

The dhanhq SDK's `MarketFeed` is synchronous (`run_forever()` then a
blocking `get_data()` loop), so it can't live directly inside FastAPI's
asyncio event loop. This runs it on its own background thread, exposes the
latest tick per security as a thread-safe read for the async harness loop,
and auto-reconnects with backoff if the socket drops — the actual
"reconnects on the websocket dropping" half of the backend-harness
definition in the README.
"""

import threading
import time
from typing import Dict, List, Optional, Tuple

from dhanhq import DhanContext, MarketFeed

from app.utils.logger import get_logger

logger = get_logger(__name__)

MAX_BACKOFF_SECONDS = 30


class DhanFeedManager:
    """
    Usage:
        feed = DhanFeedManager(dhan_context, [(MarketFeed.NSE, "1333", MarketFeed.Ticker)])
        feed.start()
        ...
        price = feed.get_last_price("1333")
        ...
        feed.stop()
    """

    def __init__(self, dhan_context: DhanContext, instruments: List[Tuple[str, str, str]]):
        self._dhan_context = dhan_context
        self._instruments = instruments
        self._feed: Optional[MarketFeed] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        self._lock = threading.Lock()
        self._latest_prices: Dict[str, float] = {}
        self._connected = False
        self._reconnect_attempts = 0
        self._last_error: Optional[str] = None

    # ── Public, read from the async harness loop ────────────────────────

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def get_last_price(self, security_id: str) -> Optional[float]:
        with self._lock:
            return self._latest_prices.get(security_id)

    def subscribe(self, security_id: str, exchange=MarketFeed.NSE, mode=MarketFeed.Ticker) -> None:
        """Add a new symbol to an already-running feed (e.g. a strategy
        registered after the harness has started)."""
        self._instruments.append((exchange, security_id, mode))
        if self._feed and self._connected:
            try:
                self._feed.subscribe_symbols([(exchange, security_id, mode)])
            except Exception as exc:
                logger.warning(f"Failed to subscribe {security_id} on live feed: {exc}")

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._run_loop, name="DhanFeedManager", daemon=True)
        self._thread.start()
        logger.info("DhanFeedManager thread started.")

    def stop(self) -> None:
        self._stop_flag.set()
        if self._feed:
            try:
                self._feed.close_connection()
            except Exception as exc:
                logger.warning(f"Error closing Dhan feed connection: {exc}")
        self._connected = False
        logger.info("DhanFeedManager stop requested.")

    # ── Internal ──────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        backoff = 2

        while not self._stop_flag.is_set():
            try:
                logger.info(f"Connecting to DhanHQ MarketFeed ({len(self._instruments)} instruments)...")
                self._feed = MarketFeed(self._dhan_context, self._instruments, "v2")
                self._feed.run_forever()
                self._connected = True
                self._reconnect_attempts = 0
                self._last_error = None
                backoff = 2

                while not self._stop_flag.is_set():
                    tick = self._feed.get_data()
                    if tick:
                        self._ingest_tick(tick)

            except Exception as exc:
                self._connected = False
                self._reconnect_attempts += 1
                self._last_error = str(exc)
                logger.error(f"DhanHQ feed error (reconnect attempt #{self._reconnect_attempts}): {exc}")

                if self._stop_flag.is_set():
                    break

                time.sleep(min(backoff, MAX_BACKOFF_SECONDS))
                backoff *= 2

        logger.info("DhanFeedManager loop exited.")

    def _ingest_tick(self, tick: dict) -> None:
        """
        NOTE: verify these key names against a real tick once you run this
        against your Dhan account — the SDK's exact `get_data()` payload
        shape isn't pinned down in the public README, so this reads a few
        plausible variants defensively rather than assuming one.
        """
        security_id = str(tick.get("security_id") or tick.get("securityId") or "")
        ltp = tick.get("LTP") or tick.get("last_traded_price") or tick.get("ltp")

        if security_id and ltp is not None:
            try:
                with self._lock:
                    self._latest_prices[security_id] = float(ltp)
            except (TypeError, ValueError):
                logger.warning(f"Ignored malformed tick for {security_id}: {tick}")
