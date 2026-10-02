"""Renew a Dhan access token before its 24-hour expiry.

Dhan rejects RenewToken once the current token is already dead, so this
runs while the token is still valid. The new token replaces the stored one
and is what the next buy or sell uses. Tokens are never written to the log.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timedelta

import httpx

from app import db
from app.auth import decrypt_secret, encrypt_secret
from app.broker.dhan_gateway import DhanRequestError, clear_sdk_client
from app.config import settings
from app.trading.nse_session import now_ist
from app.utils.logger import get_logger

logger = get_logger(__name__)

_RENEW_URL = "https://api.dhan.co/v2/RenewToken"
_BEFORE_EXPIRY = timedelta(hours=4)
_WITHOUT_EXPIRY = timedelta(hours=20)


def token_expiry(access_token: str) -> datetime | None:
    """Read the JWT `exp` claim, or None when the token is not a JWT."""
    try:
        payload = access_token.split(".")[1]
        padding = "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload + padding))
        exp = data.get("exp")
        if exp is None:
            return None
        return datetime.fromtimestamp(int(exp), tz=now_ist().tzinfo)
    except (IndexError, ValueError, TypeError, json.JSONDecodeError):
        return None


def refresh_due(access_token: str, refreshed_at: str | None, now: datetime | None = None) -> bool:
    """True when this token should be renewed.

    A JWT is renewed in the last four hours of its life. A token with no
    expiry claim is renewed 20 hours after it was saved, which is before
    Dhan's 24-hour cutoff.
    """
    moment = now or now_ist()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=now_ist().tzinfo)
    expiry = token_expiry(access_token)
    if expiry is not None:
        return moment >= expiry - _BEFORE_EXPIRY
    if not refreshed_at:
        return False
    try:
        saved = datetime.fromisoformat(refreshed_at)
    except ValueError:
        return False
    if saved.tzinfo is None:
        saved = saved.replace(tzinfo=moment.tzinfo)
    return moment - saved >= _WITHOUT_EXPIRY


def parse_renewed_token(payload: object) -> str:
    """Pull the new access token out of a RenewToken body."""
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    if not isinstance(payload, dict):
        return ""
    for key in ("accessToken", "access_token", "token"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    data = payload.get("data")
    return parse_renewed_token(data)


async def renew_access_token(client_id: str, access_token: str) -> str:
    """Ask Dhan for a new token. The current token must still be valid."""
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            _RENEW_URL,
            headers={
                "access-token": access_token,
                "dhanClientId": client_id,
                "Accept": "application/json",
            },
        )
    if response.status_code >= 400:
        raise DhanRequestError(f"Dhan token renewal failed with status {response.status_code}")
    try:
        body = response.json()
    except json.JSONDecodeError as exc:
        raise DhanRequestError("Dhan token renewal returned an unreadable body") from exc
    if isinstance(body, dict) and str(body.get("status", "")).lower() == "failure":
        raise DhanRequestError("Dhan token renewal was rejected")
    renewed = parse_renewed_token(body)
    if not renewed:
        raise DhanRequestError("Dhan token renewal did not return a token")
    return renewed


async def refresh_saved_tokens() -> None:
    """Renew due trader tokens. Skipped under pytest so a real token is not rotated."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    await refresh_saved_tokens_now()


async def refresh_saved_tokens_now() -> None:
    """Renew every saved trader token that is inside the renewal window."""
    _load_process_token()
    for user in db.list_dhan_traders():
        await _refresh_user(user)
    await _refresh_process_token()


def _load_process_token() -> None:
    """Use the last renewed process token when it outlives the one in the environment."""
    if not settings.credentials_key:
        return
    saved = db.get_process_dhan_token()
    if not saved:
        return
    try:
        stored = decrypt_secret(saved["access_token"])
    except Exception:
        logger.warning("Stored Dhan process token could not be decrypted")
        return
    if not stored:
        return
    env_exp = token_expiry(settings.dhan_access_token)
    stored_exp = token_expiry(stored)
    if stored_exp is not None and (env_exp is None or stored_exp > env_exp):
        settings.dhan_access_token = stored
        clear_sdk_client()


async def _refresh_user(user: dict) -> None:
    try:
        client_id = decrypt_secret(user.get("dhan_client_id"))
        token = decrypt_secret(user.get("dhan_access_token"))
    except Exception:
        logger.warning("Dhan token for user %s could not be decrypted", user["id"])
        return
    if not client_id or not token:
        return
    if not refresh_due(token, user.get("dhan_token_refreshed_at")):
        return
    try:
        renewed = await renew_access_token(client_id, token)
    except (DhanRequestError, httpx.HTTPError) as exc:
        logger.warning("Dhan token renewal failed for user %s: %s", user["id"], exc)
        return
    from app.broker.trading_gateway import gateway_for_user

    db.save_dhan_credentials(user["id"], encrypt_secret(client_id), encrypt_secret(renewed))
    fresh = db.get_user(user["id"])
    if fresh:
        gateway_for_user(fresh)
    logger.info("Dhan token renewed for user %s", user["id"])


async def _refresh_process_token() -> None:
    client_id = settings.dhan_client_id.strip()
    token = settings.dhan_access_token.strip()
    if not client_id or not token:
        return
    if not refresh_due(token, _process_stamp()):
        return
    try:
        renewed = await renew_access_token(client_id, token)
    except (DhanRequestError, httpx.HTTPError) as exc:
        logger.warning("Dhan process token renewal failed: %s", exc)
        return
    settings.dhan_access_token = renewed
    clear_sdk_client()
    _remember_process_stamp()
    if settings.credentials_key:
        db.save_process_dhan_token(encrypt_secret(renewed))
    logger.info("Dhan process token renewed")


_process_refreshed_at: str | None = None


def _process_stamp() -> str | None:
    return _process_refreshed_at


def _remember_process_stamp() -> None:
    global _process_refreshed_at
    _process_refreshed_at = now_ist().isoformat(timespec="seconds")
