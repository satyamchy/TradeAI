"""Production adapters for existing market, account, position and broker services.

Adapters are inert at import time. The FastAPI composition root injects the
per-user TradingGateway; this module never constructs a Dhan SDK client.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol

from app import db
from app.modules.decision_engine.schemas import (
    AccountRiskSnapshot,
    ConfirmedPosition,
    MarketSnapshot,
    StrategyPolicy,
)
from app.shared.config import Settings, settings
from app.shared.contracts import Contract
from app.trading.nse_session import (
    is_nse_cash_session_open,
    is_past_entry_cutoff,
    new_entries_blocked,
)
from app.workflows.schemas import ConfirmedOpenPosition


class GatewayProvider(Protocol):
    mode: str

    async def quote_prices(self, symbols: list[str]) -> dict[str, float]: ...
    async def fetch_candles(self, symbol: str): ...
    async def get_available_balance_inr(self) -> float: ...
    async def get_open_positions(self) -> list[dict[str, Any]]: ...
    async def get_orders(self) -> list[dict[str, Any]]: ...
    async def realized_pnl_today_inr(self) -> float: ...


class PendingExecutionReader(Protocol):
    def list_reconcilable(self, *, owner_id: int) -> list[Any]: ...


class ApprovedIntentReader(Protocol):
    def get_approved_intent(self, intent_id, *, owner_id: int): ...


class CurrentMarketReader(Protocol):
    async def get_snapshot(self, symbol: str) -> MarketSnapshot | None: ...


class Candle(Contract):
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


class CandleSeries(Contract):
    symbol: str
    observed_at: datetime
    candles: list[Candle]


class TradingGatewayMarketDataProvider:
    """Use existing Dhan quote/candle functions without changing their source."""

    def __init__(self, gateway: GatewayProvider, *, candles_fetcher=None, clock=None):
        self._gateway = gateway
        self._candles_fetcher = candles_fetcher
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def get_snapshot(self, symbol: str) -> MarketSnapshot | None:
        normalized = symbol.strip().upper()
        quotes = await self._gateway.quote_prices([normalized])
        price = quotes.get(normalized)
        if price is None or float(price) <= 0:
            return None
        captured_at = self._clock()
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise ValueError("market data clock must return a timezone-aware datetime")
        market_open = is_nse_cash_session_open(captured_at)
        return MarketSnapshot(
            symbol=normalized,
            price=Decimal(str(price)),
            captured_at=captured_at.astimezone(timezone.utc),
            market_open=market_open,
            entries_allowed=(
                market_open and not is_past_entry_cutoff(captured_at) and not new_entries_blocked()
            ),
        )

    async def get_candles(self, symbol: str) -> CandleSeries | None:
        """Return the existing 15-minute candle series with its retrieval time.

        The legacy Dhan candle API does not return usable bar timestamps, so
        `observed_at` records retrieval time and is not represented as each
        candle's exchange timestamp. Entry decisions use the separate live quote.
        """
        fetcher = self._candles_fetcher or self._gateway.fetch_candles
        frame = await fetcher(symbol)
        if frame is None or frame.empty:
            return None
        observed_at = self._clock()
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("market data clock must return a timezone-aware datetime")
        candles = [
            Candle(
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=int(float(row["volume"])),
            )
            for _, row in frame.iterrows()
        ]
        return CandleSeries(
            symbol=symbol.strip().upper(),
            observed_at=observed_at.astimezone(timezone.utc),
            candles=candles,
        )


def risk_configuration(config: Settings = settings) -> dict[str, Decimal | int]:
    """Load the single existing risk configuration and apply app defaults."""
    saved = db.get_risk_settings() or {}
    return {
        "max_positions": int(saved.get("max_positions", config.max_positions)),
        "capital_per_trade_pct": Decimal(str(saved.get("capital_per_trade_pct", config.capital_per_trade_pct))),
        "cash_reserve_pct": Decimal(str(saved.get("cash_reserve_pct", config.cash_reserve_pct))),
        "take_profit_pct": Decimal(str(saved.get("take_profit_pct", config.take_profit_pct))),
        "stop_loss_pct": Decimal(str(saved.get("stop_loss_pct", config.stop_loss_pct))),
        "max_daily_loss_inr": Decimal(str(saved.get("max_daily_loss_inr", config.max_daily_loss_inr))),
    }


class TradingGatewayAccountRiskProvider:
    """Build provider-neutral capital, exposure, daily-loss and limit snapshots."""

    def __init__(
        self,
        gateway: GatewayProvider,
        *,
        owner_id: int,
        market_data: CurrentMarketReader | None = None,
        pending_executions: PendingExecutionReader | None = None,
        approved_intents: ApprovedIntentReader | None = None,
        config: Settings = settings,
        clock=None,
    ):
        self._gateway = gateway
        self._owner_id = owner_id
        self._market_data = market_data
        self._pending_executions = pending_executions
        self._approved_intents = approved_intents
        self._config = config
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def get_snapshot(self, *, owner_id: int) -> AccountRiskSnapshot | None:
        if owner_id != self._owner_id:
            return None
        available = Decimal(str(await self._gateway.get_available_balance_inr()))
        raw_positions = await self._gateway.get_open_positions()
        positions: list[ConfirmedPosition] = []
        blocked_symbols: list[str] = []
        exposure = Decimal("0")
        unrealized = Decimal("0")
        market_times: list[datetime] = []
        for raw in raw_positions:
            quantity = int(raw.get("quantity") or 0)
            average = Decimal(str(raw.get("average_price") or 0))
            last = Decimal(str(raw.get("last_price") or raw.get("average_price") or 0))
            symbol = str(raw.get("symbol") or "").strip().upper()
            security_id = str(raw.get("security_id") or "").strip()
            if not symbol or quantity == 0 or average <= 0:
                continue
            if quantity < 0 or not security_id:
                blocked_symbols.append(symbol)
            if self._market_data is not None:
                market = await self._market_data.get_snapshot(symbol)
                if market is None:
                    return None
                last = market.price
                market_times.append(market.captured_at)
            exposure += abs(quantity) * last
            unrealized += (last - average) * quantity
            if quantity > 0 and security_id:
                positions.append(
                    ConfirmedPosition(
                        symbol=symbol,
                        security_id=security_id,
                        quantity=quantity,
                        average_price=average,
                        market_value=last * quantity,
                    )
                )
        realized = Decimal(str(await self._gateway.realized_pnl_today_inr()))
        daily_loss = max(Decimal("0"), -(realized + unrealized))
        limits = risk_configuration(self._config)
        pending_symbols: list[str] = []
        if self._pending_executions is not None:
            for order in self._pending_executions.list_reconcilable(owner_id=owner_id):
                if self._approved_intents is None:
                    continue
                intent = self._approved_intents.get_approved_intent(
                    order.order_intent_id, owner_id=owner_id
                )
                if intent is not None:
                    pending_symbols.append(intent.symbol)
        captured_at = min(market_times) if market_times else self._clock()
        return AccountRiskSnapshot(
            captured_at=captured_at.astimezone(timezone.utc),
            available_funds=max(available, Decimal("0")),
            # The paper ledger has no leverage; its unreserved cash is also the
            # available margin and is the strictest usable capital amount.
            available_margin=max(available, Decimal("0")),
            total_exposure=max(exposure, Decimal("0")),
            daily_loss=daily_loss,
            kill_switch_enabled=False,
            pending_symbols=pending_symbols,
            blocked_symbols=blocked_symbols,
            confirmed_positions=positions,
            configured_limits=limits,
        )


class TradingGatewayConfirmedPositionProvider:
    """Expose only open positions returned by the configured paper gateway."""

    def __init__(self, gateway: GatewayProvider, *, owner_id: int, clock=None):
        self._gateway = gateway
        self._owner_id = owner_id
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def get_open_position(
        self, *, owner_id: int, symbol: str, security_id: str, product_type: str
    ) -> ConfirmedOpenPosition | None:
        if owner_id != self._owner_id:
            return None
        for raw in await self._gateway.get_open_positions():
            quantity = int(raw.get("quantity") or 0)
            if (
                str(raw.get("symbol") or "").upper() == symbol.upper()
                and str(raw.get("security_id") or "") == security_id
                and str(raw.get("product_type") or "INTRADAY").upper() == product_type.upper()
                and quantity > 0
            ):
                average = Decimal(str(raw.get("average_price") or 0))
                if average <= 0:
                    return None
                return ConfirmedOpenPosition(
                    quantity=quantity,
                    average_price=average,
                    opened_at=self._clock().astimezone(timezone.utc),
                )
        return None


def build_strategy_policy(config: Settings = settings) -> StrategyPolicy:
    """Map the current persisted risk settings to Module 3's explicit policy."""
    limits = risk_configuration(config)
    cash_reserve = Decimal(limits["cash_reserve_pct"])
    if not Decimal("0") <= cash_reserve < Decimal("1"):
        raise ValueError("cash_reserve_pct must be between 0 and 1")
    spendable_cap = Decimal(str(config.paper_starting_balance_inr)) * (Decimal("1") - cash_reserve)
    return StrategyPolicy(
        key="TRADEX_INTRADAY_LONG",
        version="1",
        max_risk_amount=Decimal(limits["max_daily_loss_inr"]),
        risk_budget_fraction=Decimal(limits["capital_per_trade_pct"]),
        max_order_value=spendable_cap,
        max_symbol_exposure=spendable_cap,
        max_total_exposure=spendable_cap,
        max_daily_loss=Decimal(limits["max_daily_loss_inr"]),
        stop_loss_pct=Decimal(limits["stop_loss_pct"]),
        target_pct=Decimal(limits["take_profit_pct"]),
        max_positions=int(limits["max_positions"]),
        product_type="INTRADAY",
        order_type="MARKET",
    )
