"""Paper-cycle checks. These tests never call the Dhan order endpoint."""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.broker import dhan_gateway
from app.broker.paper_ledger import PaperLedger
from app.trading import intraday_cycle
from app.trading.automation_runner import AutomationRunner
from app.trading.nse_session import (
    is_nse_cash_session_open,
    is_past_entry_cutoff,
    is_square_off_time,
)
from app.trading.risk_limits import RiskLimits, unrealized_pnl_percent
from app.trading.screener import order_candidates, score_candles

IST = ZoneInfo("Asia/Kolkata")
# Thursday 1 Oct 2026 is a weekday. Saturday 3 Oct 2026 is closed.
OPEN = datetime(2026, 10, 1, 10, 0, tzinfo=IST)
CUTOFF = datetime(2026, 10, 1, 14, 50, tzinfo=IST)
SQUARE_OFF = datetime(2026, 10, 1, 15, 20, tzinfo=IST)
CLOSED = datetime(2026, 10, 3, 10, 0, tzinfo=IST)


def _limits(**overrides) -> RiskLimits:
    values = dict(
        max_positions=2,
        capital_per_trade_pct=0.20,
        cash_reserve_pct=0.10,
        take_profit_pct=1.5,
        stop_loss_pct=1.0,
        max_daily_loss_inr=2_000,
        screener_limit=1,
        cycle_interval_seconds=30,
    )
    values.update(overrides)
    return RiskLimits(**values)


class PaperAccount:
    """Ledger plus a fixed security id. It has no path to the Dhan order call."""

    def __init__(self, ledger: PaperLedger):
        self.mode = "paper"
        self.ledger = ledger

    async def get_available_balance_inr(self) -> float:
        return self.ledger.available_balance_inr()

    async def get_open_positions(self) -> list[dict]:
        return self.ledger.open_positions()

    async def get_orders(self) -> list[dict]:
        return self.ledger.orders()

    async def resolve_security_id(self, symbol: str) -> str:
        return "1001"

    async def place_intraday_order(self, symbol, security_id, side, quantity, price, product_type="INTRADAY") -> dict:
        return self.ledger.fill_intraday_order(
            symbol, security_id, side, quantity, price, product_type=product_type
        )

    async def set_last_price(self, symbol: str, last_price: float, product_type: str = "INTRADAY") -> None:
        self.ledger.set_last_price(symbol, last_price, product_type)

    async def realized_pnl_today_inr(self) -> float:
        return self.ledger.realized_pnl_today_inr()


def _patch_market(monkeypatch):
    async def prices(symbols):
        return {symbol: 100.0 if symbol == "RELIANCE" else 50.0 for symbol in symbols}

    async def rank(side, exclude=None, limit=None, index=None):
        exclude = exclude or set()
        if side == "short":
            rows = [{"symbol": "TCS", "ltp": 50.0, "score": -2.0}]
        else:
            rows = [
                {"symbol": "RELIANCE", "ltp": 100.0, "score": 5.0},
                {"symbol": "TCS", "ltp": 50.0, "score": 4.0},
            ]
        return [row for row in rows if row["symbol"] not in exclude][: limit or len(rows)]

    monkeypatch.setattr(intraday_cycle, "last_traded_prices", prices)
    monkeypatch.setattr(intraday_cycle, "rank_nifty50", rank)


def _forbid_live_orders(monkeypatch):
    async def place(*args, **kwargs):
        raise AssertionError("a live Dhan order was sent")

    monkeypatch.setattr(dhan_gateway, "place_market_order", place)


def test_session_clock():
    assert is_nse_cash_session_open(OPEN)
    assert not is_nse_cash_session_open(CLOSED)
    assert is_past_entry_cutoff(CUTOFF)
    assert not is_past_entry_cutoff(OPEN)
    assert is_square_off_time(SQUARE_OFF)
    assert not is_square_off_time(OPEN)


def test_short_pnl_is_inverted():
    assert unrealized_pnl_percent(100, 110, 10) == pytest.approx(10)
    assert unrealized_pnl_percent(100, 90, -10) == pytest.approx(10)
    assert unrealized_pnl_percent(100, 110, -10) == pytest.approx(-10)


def test_paper_short_reserves_cash_and_books_profit(tmp_path):
    ledger = PaperLedger(str(tmp_path / "paper.json"), 100_000)
    ledger.fill_intraday_order("TCS", "1001", "SELL", 10, 100)
    assert ledger.available_balance_inr() == pytest.approx(99_000)
    assert ledger.open_positions()[0]["quantity"] == -10
    ledger.fill_intraday_order("TCS", "1001", "BUY", 10, 90)
    assert ledger.open_positions() == []
    assert ledger.available_balance_inr() == pytest.approx(100_100)
    assert ledger.realized_pnl_today_inr() == pytest.approx(100)


def test_screener_ranks_long_above_short():
    frame = _tradeable_frame()
    scored = score_candles("RELIANCE", frame)
    assert scored is not None
    weak = dict(scored)
    weak["symbol"] = "TCS"
    weak["score"] = scored["score"] - 1
    assert order_candidates([scored, weak], "long", 1)[0]["symbol"] == "RELIANCE"
    assert order_candidates([scored, weak], "short", 1)[0]["symbol"] == "TCS"


def test_closed_session_does_not_trade(tmp_path, monkeypatch):
    _forbid_live_orders(monkeypatch)
    _patch_market(monkeypatch)
    account = PaperAccount(PaperLedger(str(tmp_path / "paper.json"), 100_000))
    runner = AutomationRunner(gateway=account)
    runner.enable(["intraday_long"])

    async def scenario():
        assert await runner.run_once(CLOSED) is None
        assert account.ledger.open_positions() == []
        status = await runner.status(CLOSED)
        assert status["enabled"] is True
        assert status["next_action"] == "waiting_for_session"

    asyncio.run(scenario())


def test_paper_cycle_then_disable_blocks_the_next_entry(tmp_path, monkeypatch):
    _forbid_live_orders(monkeypatch)
    _patch_market(monkeypatch)
    account = PaperAccount(PaperLedger(str(tmp_path / "paper.json"), 100_000))
    runner = AutomationRunner(gateway=account)
    runner.limits = _limits()
    runner.enable(["intraday_long"])

    async def scenario():
        first = await runner.run_once(OPEN)
        assert first["entries"][0]["symbol"] == "RELIANCE"
        assert first["entries"][0]["status"] == "PLACED"
        assert len(account.ledger.open_positions()) == 1

        runner.disable()
        second = await runner.run_once(OPEN)
        assert second["entries"] == []
        assert [row["symbol"] for row in account.ledger.open_positions()] == ["RELIANCE"]

    asyncio.run(scenario())


def test_short_entry_and_square_off(tmp_path, monkeypatch):
    _forbid_live_orders(monkeypatch)
    _patch_market(monkeypatch)
    account = PaperAccount(PaperLedger(str(tmp_path / "paper.json"), 100_000))
    runner = AutomationRunner(gateway=account)
    runner.limits = _limits(screener_limit=1)
    runner.enable(["intraday_short"])

    async def scenario():
        snapshot = await runner.run_once(OPEN)
        assert snapshot["entries"][0]["side"] == "SELL"
        assert account.ledger.open_positions()[0]["quantity"] < 0

        flat = await runner.square_off_open_positions(OPEN)
        assert flat["exits"][0]["exit_reason"] == "square-off"
        assert flat["exits"][0]["side"] == "BUY"
        assert account.ledger.open_positions() == []

    asyncio.run(scenario())


def test_entry_cutoff_blocks_new_orders(tmp_path, monkeypatch):
    _forbid_live_orders(monkeypatch)
    _patch_market(monkeypatch)
    account = PaperAccount(PaperLedger(str(tmp_path / "paper.json"), 100_000))
    runner = AutomationRunner(gateway=account)
    runner.limits = _limits()
    runner.enable(["intraday_long"])

    async def scenario():
        snapshot = await runner.run_once(CUTOFF)
        assert snapshot["entries"] == []
        assert account.ledger.open_positions() == []

    asyncio.run(scenario())


def test_enable_route_stays_off_until_called(tmp_path, monkeypatch):
    from app import db
    from app.auth import hash_password
    from app.config import settings
    from main import app

    monkeypatch.setattr(settings, "database_path", str(tmp_path / "tradex.db"))
    db.init_db()
    db.create_user("trader1", hash_password("password1"), "trader")

    with TestClient(app) as client:
        logged_out = client.get("/api/v1/automation/status")
        assert logged_out.status_code == 401
        login = client.post("/api/v1/auth/login", json={"username": "trader1", "password": "password1"})
        assert login.status_code == 200
        status = client.get("/api/v1/automation/status")
        assert status.status_code == 200
        assert status.json()["enabled"] is False
        enabled = client.post("/api/v1/automation/enable", json={"methods": ["intraday_long"]})
        assert enabled.status_code == 200
        body = enabled.json()
        assert body["enabled"] is True
        assert body["mode"] == settings.trading_mode.strip().lower()
        disabled = client.post("/api/v1/automation/disable")
        assert disabled.status_code == 200
        assert disabled.json()["enabled"] is False


def test_a_later_fill_keeps_the_earlier_one(tmp_path):
    path = str(tmp_path / "paper.json")
    first = PaperLedger(path, 100_000)
    second = PaperLedger(path, 100_000)
    first.fill_intraday_order("TCS", "1", "BUY", 10, 100)
    second.fill_intraday_order("INFY", "2", "BUY", 10, 100)
    saved = PaperLedger(path, 100_000)
    assert {row["symbol"] for row in saved.open_positions()} == {"INFY", "TCS"}


def test_delivery_sell_without_shares_is_rejected(tmp_path):
    from app.broker.paper_ledger import PaperLedgerError

    ledger = PaperLedger(str(tmp_path / "paper.json"), 100_000)
    with pytest.raises(PaperLedgerError):
        ledger.fill_intraday_order("TCS", "1", "SELL", 1, 100, product_type="DELIVERY")


def test_security_id_drops_the_decimal():
    from app.broker.dhan_gateway import normalize_security_id

    assert normalize_security_id("1234.0") == "1234"
    assert normalize_security_id(1234.0) == "1234"


def test_holiday_is_a_closed_session():
    from app.trading.nse_session import new_entries_blocked, set_holidays

    set_holidays({"2026-10-01"})
    try:
        assert not is_nse_cash_session_open(OPEN)
    finally:
        set_holidays(set(), "unknown")
    assert is_nse_cash_session_open(OPEN)
    set_holidays(set(), "failed")
    try:
        assert new_entries_blocked()
    finally:
        set_holidays(set(), "unknown")


def _tradeable_frame() -> pd.DataFrame:
    bars = 40
    index = np.arange(bars)
    close = 100 + np.sin(index / 3) * 2
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1.5,
            "low": close - 1.5,
            "close": close,
            "volume": np.full(bars, 1_000.0),
        }
    )
