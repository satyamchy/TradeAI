"""Dhan token renewal. These tests never call the live RenewToken endpoint."""

import asyncio
import base64
import json
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet

from app.broker.dhan_token import parse_renewed_token, refresh_due, refresh_saved_tokens, token_expiry

IST = timezone(timedelta(hours=5, minutes=30))


def _jwt(exp: int) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"header.{payload}.sig"


def test_expiry_is_read_from_the_jwt():
    exp = 1_800_000_000
    assert token_expiry(_jwt(exp)) == datetime.fromtimestamp(exp, tz=IST)
    assert token_expiry("not-a-jwt") is None


def test_token_is_due_only_near_expiry():
    now = datetime(2026, 10, 5, 9, 0, tzinfo=IST)
    soon = int((now + timedelta(hours=2)).timestamp())
    later = int((now + timedelta(hours=20)).timestamp())
    assert refresh_due(_jwt(soon), None, now)
    assert not refresh_due(_jwt(later), None, now)
    assert not refresh_due("opaque", now.isoformat(), now)
    assert refresh_due("opaque", (now - timedelta(hours=21)).isoformat(), now)


def test_renewal_body_can_be_either_shape():
    assert parse_renewed_token({"accessToken": "abc"}) == "abc"
    assert parse_renewed_token({"data": {"token": "xyz"}}) == "xyz"
    assert parse_renewed_token({}) == ""


def test_due_trader_token_is_replaced(tmp_path, monkeypatch):
    from app import db
    from app.auth import decrypt_secret, hash_password
    from app.broker import dhan_token
    from app.config import settings

    monkeypatch.setattr(settings, "database_path", str(tmp_path / "tradex.db"))
    monkeypatch.setattr(settings, "paper_ledger_dir", str(tmp_path / "ledgers"))
    monkeypatch.setattr(settings, "credentials_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "dhan_client_id", "")
    monkeypatch.setattr(settings, "dhan_access_token", "")
    db.init_db()
    user = db.create_user("trader1", hash_password("password1"), "trader")
    soon = int((datetime.now(IST) + timedelta(hours=1)).timestamp())
    current = _jwt(soon)
    from app.auth import encrypt_secret

    db.save_dhan_credentials(user["id"], encrypt_secret("100000"), encrypt_secret(current))

    async def renew(client_id, access_token):
        assert client_id == "100000"
        assert access_token == current
        return "renewed-token"

    monkeypatch.setattr(dhan_token, "renew_access_token", renew)
    asyncio.run(dhan_token.refresh_saved_tokens_now())
    saved = db.get_user(user["id"])
    assert decrypt_secret(saved["dhan_access_token"]) == "renewed-token"


def test_scheduler_does_not_call_dhan_during_pytest(monkeypatch):
    called = {"n": 0}

    async def boom():
        called["n"] += 1

    monkeypatch.setattr("app.broker.dhan_token.refresh_saved_tokens_now", boom)
    asyncio.run(refresh_saved_tokens())
    assert called["n"] == 0
