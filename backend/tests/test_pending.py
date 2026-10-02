"""A suggestion or delivery request is not an order until Execute."""

import pytest
from fastapi.testclient import TestClient

from app.broker import dhan_gateway
from app.trading.suggestions import accept_model_choice


def test_model_choice_must_be_one_of_the_offered_names():
    choices = [{"symbol": "RELIANCE", "side": "BUY", "ltp": 100.0}]
    picked = accept_model_choice('{"symbol": "RELIANCE", "side": "BUY", "quantity": 99}', choices)
    assert picked == {"symbol": "RELIANCE", "side": "BUY", "price": 100.0}
    assert accept_model_choice('{"symbol": "NOTREAL", "side": "BUY"}', choices) is None
    assert accept_model_choice("buy RELIANCE", choices) is None


def test_delivery_is_not_filled_until_execute(tmp_path, monkeypatch):
    from app import db
    from app.auth import hash_password
    from app.config import settings
    from main import app

    monkeypatch.setattr(settings, "database_path", str(tmp_path / "tradex.db"))
    monkeypatch.setattr(settings, "paper_ledger_dir", str(tmp_path / "ledgers"))
    monkeypatch.setattr(settings, "trading_mode", "paper")
    monkeypatch.setattr(dhan_gateway, "is_dhan_configured", lambda: False)

    calls = {"live": 0}

    async def place(*args, **kwargs):
        calls["live"] += 1
        raise AssertionError("a pending row reached Dhan")

    async def prices(symbols):
        return {symbol: 100.0 for symbol in symbols}

    monkeypatch.setattr(dhan_gateway, "place_market_order", place)
    monkeypatch.setattr("app.trading.pending.last_traded_prices", prices)
    monkeypatch.setattr("app.trading.pending.is_nse_cash_session_open", lambda moment=None: True)
    monkeypatch.setattr("app.trading.pending.is_past_entry_cutoff", lambda moment=None: False)
    monkeypatch.setattr("app.trading.pending.is_square_off_time", lambda moment=None: False)

    db.init_db()
    db.create_user("trader1", hash_password("password1"), "trader")
    db.create_user("viewer1", hash_password("password1"), "viewer")

    with TestClient(app) as client:
        assert client.post("/api/v1/auth/login", json={"username": "trader1", "password": "password1"}).status_code == 200
        saved = client.post("/api/v1/orders/delivery", json={"symbol": "RELIANCE", "side": "BUY", "quantity": 1})
        assert saved.status_code == 200
        pending_id = saved.json()["id"]
        listed = client.get("/api/v1/orders/pending")
        assert listed.status_code == 200
        assert [row["id"] for row in listed.json()["orders"]] == [pending_id]
        positions = client.get("/api/v1/account/positions")
        assert positions.json()["count"] == 0
        assert calls["live"] == 0

        executed = client.post(f"/api/v1/orders/pending/{pending_id}/execute")
        assert executed.status_code == 200
        assert calls["live"] == 0
        assert client.get("/api/v1/orders/pending").json()["orders"] == []
        assert client.get("/api/v1/account/positions").json()["count"] == 1

        events = client.get("/api/v1/events")
        actions = [row["action"] for row in events.json()["events"]]
        assert "delivery_request" in actions
        assert "execute" in actions

        client.post("/api/v1/auth/logout")
        assert client.post("/api/v1/auth/login", json={"username": "viewer1", "password": "password1"}).status_code == 200
        refused = client.post("/api/v1/orders/delivery", json={"symbol": "TCS", "side": "BUY", "quantity": 1})
        assert refused.status_code == 403


def test_second_execute_does_not_place_again(tmp_path, monkeypatch):
    from app import db
    from app.auth import hash_password
    from app.config import settings
    from main import app

    monkeypatch.setattr(settings, "database_path", str(tmp_path / "tradex.db"))
    monkeypatch.setattr(settings, "paper_ledger_dir", str(tmp_path / "ledgers"))
    monkeypatch.setattr(settings, "trading_mode", "paper")
    monkeypatch.setattr(dhan_gateway, "is_dhan_configured", lambda: False)

    async def prices(symbols):
        return {symbol: 100.0 for symbol in symbols}

    monkeypatch.setattr("app.trading.pending.last_traded_prices", prices)
    monkeypatch.setattr("app.trading.pending.is_nse_cash_session_open", lambda moment=None: True)
    monkeypatch.setattr("app.trading.pending.is_past_entry_cutoff", lambda moment=None: False)
    monkeypatch.setattr("app.trading.pending.is_square_off_time", lambda moment=None: False)

    db.init_db()
    db.create_user("trader1", hash_password("password1"), "trader")

    with TestClient(app) as client:
        assert client.post("/api/v1/auth/login", json={"username": "trader1", "password": "password1"}).status_code == 200
        saved = client.post("/api/v1/orders/delivery", json={"symbol": "RELIANCE", "side": "BUY", "quantity": 1})
        pending_id = saved.json()["id"]
        assert client.post(f"/api/v1/orders/pending/{pending_id}/execute").status_code == 200
        again = client.post(f"/api/v1/orders/pending/{pending_id}/execute")
        assert again.status_code == 400
        assert client.get("/api/v1/account/positions").json()["count"] == 1


def test_closing_sell_is_not_blocked_by_the_entry_cap(tmp_path, monkeypatch):
    from app import db
    from app.auth import hash_password
    from app.config import settings
    from app.trading import pending as pending_module
    from main import app

    monkeypatch.setattr(settings, "database_path", str(tmp_path / "tradex.db"))
    monkeypatch.setattr(settings, "paper_ledger_dir", str(tmp_path / "ledgers"))
    monkeypatch.setattr(settings, "trading_mode", "paper")
    monkeypatch.setattr(dhan_gateway, "is_dhan_configured", lambda: False)

    async def prices(symbols):
        return {symbol: 100.0 for symbol in symbols}

    def blocked(**kwargs):
        return "order is above the per-trade cash cap"

    monkeypatch.setattr("app.trading.pending.last_traded_prices", prices)
    monkeypatch.setattr("app.trading.pending.is_nse_cash_session_open", lambda moment=None: True)
    monkeypatch.setattr("app.trading.pending.is_past_entry_cutoff", lambda moment=None: False)
    monkeypatch.setattr("app.trading.pending.is_square_off_time", lambda moment=None: False)
    monkeypatch.setattr(pending_module, "check_new_entry", blocked)

    db.init_db()
    db.create_user("trader1", hash_password("password1"), "trader")

    with TestClient(app) as client:
        assert client.post("/api/v1/auth/login", json={"username": "trader1", "password": "password1"}).status_code == 200
        # Seed the long directly so the entry cap is not what creates it.
        from app.broker.trading_gateway import gateway_for_user

        user = db.get_user_by_username("trader1")
        gateway_for_user(user)._paper.fill_intraday_order("RELIANCE", "RELIANCE", "BUY", 1, 100, product_type="DELIVERY")
        saved = client.post("/api/v1/orders/delivery", json={"symbol": "RELIANCE", "side": "SELL", "quantity": 1})
        assert saved.status_code == 200
        executed = client.post(f"/api/v1/orders/pending/{saved.json()['id']}/execute")
        assert executed.status_code == 200
        assert client.get("/api/v1/account/positions").json()["count"] == 0


def test_square_off_stops_new_entries(tmp_path, monkeypatch):
    from app import db
    from app.auth import hash_password
    from app.config import settings
    from main import app

    monkeypatch.setattr(settings, "database_path", str(tmp_path / "tradex.db"))
    monkeypatch.setattr(settings, "paper_ledger_dir", str(tmp_path / "ledgers"))
    monkeypatch.setattr(settings, "trading_mode", "paper")
    monkeypatch.setattr("app.api.automation.is_nse_cash_session_open", lambda moment=None: False)
    monkeypatch.setattr("app.trading.automation_runner.is_nse_cash_session_open", lambda moment=None: False)

    db.init_db()
    db.create_user("trader1", hash_password("password1"), "trader")

    with TestClient(app) as client:
        assert client.post("/api/v1/auth/login", json={"username": "trader1", "password": "password1"}).status_code == 200
        assert client.post("/api/v1/automation/enable", json={"methods": ["intraday_long"]}).status_code == 200
        square = client.post("/api/v1/automation/square-off-open-positions")
        assert square.status_code == 400
        status = client.get("/api/v1/automation/status")
        assert status.json()["enabled"] is False
        assert status.json()["automation_state"] == "exits_only"
