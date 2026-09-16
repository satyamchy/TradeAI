"""
Coordinates independent strategies so they don't step on each other — the
harness's answer to "two strategies both trying to buy the same stock".

Each symbol gets exactly one asyncio.Lock. Before the harness executes an
OrderIntent for a symbol, it must hold that symbol's lock; any other
strategy targeting the same symbol waits its turn instead of racing to
place a duplicate order in the same tick.
"""

import asyncio
from typing import Dict, List

from app.harness.base_strategy import BaseStrategy
from app.utils.logger import get_logger

logger = get_logger(__name__)


class StrategyCoordinator:
    def __init__(self):
        self._strategies: Dict[str, BaseStrategy] = {}
        self._symbol_locks: Dict[str, asyncio.Lock] = {}

    def register(self, strategy: BaseStrategy) -> None:
        if strategy.name in self._strategies:
            raise ValueError(f"Strategy '{strategy.name}' is already registered.")
        self._strategies[strategy.name] = strategy
        self._symbol_locks.setdefault(strategy.symbol, asyncio.Lock())
        logger.info(f"Strategy registered: {strategy.name} (symbol={strategy.symbol})")

    def unregister(self, name: str) -> None:
        self._strategies.pop(name, None)
        logger.info(f"Strategy unregistered: {name}")

    def list_strategies(self) -> List[dict]:
        return [
            {"name": s.name, "symbol": s.symbol, "security_id": s.security_id}
            for s in self._strategies.values()
        ]

    @property
    def strategies(self) -> List[BaseStrategy]:
        return list(self._strategies.values())

    def lock_for(self, symbol: str) -> asyncio.Lock:
        return self._symbol_locks.setdefault(symbol, asyncio.Lock())
