"""Authentication, authorization and credential encryption shared by routes."""

from __future__ import annotations

import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request

from app import db
from app.shared.config import settings

ROLES = ("admin", "trader", "viewer")


def hash_password(password: str) -> str:
    """Return a one-way password hash."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def password_matches(password: str, password_hash: str) -> bool:
    """Compare a password to its stored hash."""
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def _fernet() -> Fernet:
    if not settings.credentials_key:
        raise HTTPException(status_code=400, detail="CREDENTIALS_KEY is not set")
    try:
        return Fernet(settings.credentials_key.encode())
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail="CREDENTIALS_KEY is not a valid Fernet key") from exc


def encrypt_secret(value: str) -> str:
    """Encrypt a Dhan client id or access token for storage."""
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str | None) -> str:
    """Decrypt stored credentials, returning an empty value when absent."""
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise HTTPException(status_code=500, detail="Stored Dhan credentials could not be decrypted") from exc


def ensure_admin() -> None:
    """Create the initial administrator only when the database has no users."""
    if db.user_count() or not settings.admin_password:
        return
    db.create_user(settings.admin_username, hash_password(settings.admin_password), "admin")


def current_user(request: Request) -> dict:
    """Return the active session user or raise 401."""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Login required")
    user = db.get_user(int(user_id))
    if user is None or user["disabled"]:
        raise HTTPException(status_code=401, detail="Login required")
    return user


def require_trader(request: Request) -> dict:
    """Require an enabled trader session."""
    user = current_user(request)
    if user["role"] != "trader":
        raise HTTPException(status_code=403, detail="Only a trader can do this")
    return user


def require_admin(request: Request) -> dict:
    """Require an enabled admin session."""
    user = current_user(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only an admin can do this")
    return user


def public_user(user: dict) -> dict:
    """Return browser-safe account fields; never include password/token data."""
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "disabled": user["disabled"],
        "dhan_saved": user["dhan_saved"],
        "automation_state": user["automation_state"],
        "automation_methods": user["automation_methods"],
        "trading_index": user.get("trading_index") or "NIFTY 50",
    }
