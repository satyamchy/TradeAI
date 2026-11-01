import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pandas as pd
from app.modules.decision_engine.schemas import AccountRiskSnapshot, MarketSnapshot
from app.shared.providers import (
    TradingGatewayAccountRiskProvider,
    TradingGatewayConfirmedPositionProvider,
    TradingGatewayMarketDataProvider,
)


class ProviderGateway:
    mode = "paper"

    async def quote_prices(self, symbols):
        return {"RELIANCE": 123.45}

    async def fetch_candles(self, symbol):
        return pd.DataFrame(
            [
                {"open": 100, "high": 105, "low": 98, "close": 102, "volume": 500},
                {"open": 102, "high": 125, "low": 101, "close": 123, "volume": 700},
            ]
        )

    async def get_available_balance_inr(self):
        return 1_000

    async def get_open_positions(self):
        return [
            {
                "symbol": "RELIANCE",
                "security_id": "2885",
                "quantity": 10,
                "average_price": 100,
                "last_price": 90,
                "product_type": "INTRADAY",
            },
            {
                "symbol": "OLD_SHORT",
                "security_id": "44",
                "quantity": -2,
                "average_price": 50,
                "last_price": 45,
                "product_type": "INTRADAY",
            },
        ]

    async def realized_pnl_today_inr(self):
        return -50

    async def get_orders(self):
        return []


class PendingOrders:
    def __init__(self, intent_id):
        self.intent_id = intent_id

    def list_reconcilable(self, *, owner_id):
        assert owner_id == 9
        return [SimpleNamespace(order_intent_id=self.intent_id)]


class ApprovedIntents:
    def __init__(self, intent_id):
        self.intent_id = intent_id

    def get_approved_intent(self, intent_id, *, owner_id):
        assert owner_id == 9
        if intent_id == self.intent_id:
            return SimpleNamespace(symbol="TCS")
        return None


def test_market_provider_adapts_current_quote_and_candle_series(monkeypatch):
    observed = datetime(2026, 10, 30, 6, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("app.shared.providers.is_nse_cash_session_open", lambda value: True)
    provider = TradingGatewayMarketDataProvider(
        ProviderGateway(), clock=lambda: observed
    )

    async def run():
        return await provider.get_snapshot("reliance"), await provider.get_candles("reliance")

    snapshot, candles = asyncio.run(run())

    assert snapshot == MarketSnapshot(
        symbol="RELIANCE",
        price=Decimal("123.45"),
        captured_at=observed,
        market_open=True,
    )
    assert candles is not None and candles.symbol == "RELIANCE"
    assert candles.observed_at == observed
    assert [(row.close, row.volume) for row in candles.candles] == [
        (Decimal("102"), 500),
        (Decimal("123"), 700),
    ]


def test_account_provider_returns_confirmed_exposure_pnl_limits_and_pending_symbols(monkeypatch):
    monkeypatch.setattr(
        "app.shared.providers.db.get_risk_settings",
        lambda: {
            "max_positions": 3,
            "capital_per_trade_pct": 0.25,
            "cash_reserve_pct": 0.15,
            "take_profit_pct": 2.0,
            "stop_loss_pct": 1.0,
            "max_daily_loss_inr": 500,
        },
    )
    intent_id = uuid4()
    provider = TradingGatewayAccountRiskProvider(
        ProviderGateway(),
        owner_id=9,
        pending_executions=PendingOrders(intent_id),
        approved_intents=ApprovedIntents(intent_id),
        clock=lambda: datetime(2026, 10, 30, 6, 0, tzinfo=timezone.utc),
    )

    snapshot = asyncio.run(provider.get_snapshot(owner_id=9))

    assert isinstance(snapshot, AccountRiskSnapshot)
    assert snapshot.available_funds == Decimal("1000")
    assert snapshot.available_margin == Decimal("1000")
    assert snapshot.total_exposure == Decimal("990")
    assert snapshot.daily_loss == Decimal("140")
    assert snapshot.pending_symbols == ["TCS"]
    assert snapshot.blocked_symbols == ["OLD_SHORT"]
    assert snapshot.configured_limits["max_positions"] == 3
    assert len(snapshot.confirmed_positions) == 1
    assert snapshot.confirmed_positions[0].market_value == Decimal("900")
    assert asyncio.run(provider.get_snapshot(owner_id=10)) is None


def test_position_provider_only_returns_matching_positive_confirmed_position():
    provider = TradingGatewayConfirmedPositionProvider(
        ProviderGateway(),
        owner_id=9,
        clock=lambda: datetime(2026, 10, 30, 6, 0, tzinfo=timezone.utc),
    )

    async def run():
        position = await provider.get_open_position(
            owner_id=9,
            symbol="RELIANCE",
            security_id="2885",
            product_type="INTRADAY",
        )
        other_owner = await provider.get_open_position(
            owner_id=10,
            symbol="RELIANCE",
            security_id="2885",
            product_type="INTRADAY",
        )
        short_position = await provider.get_open_position(
            owner_id=9,
            symbol="OLD_SHORT",
            security_id="44",
            product_type="INTRADAY",
        )
        return position, other_owner, short_position

    position, other_owner, short_position = asyncio.run(run())

    assert position is not None
    assert position.quantity == 10
    assert position.average_price == Decimal("100")
    assert other_owner is None
    assert short_position is None
