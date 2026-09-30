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
