"""Passwords, Dhan ciphertext, and the signed session cookie.

Login passwords are hashed. Dhan client id and access token are encrypted
with CREDENTIALS_KEY so they can be sent to Dhan later. A hash cannot do that.
"""

from __future__ import annotations

import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request

from app import db
from app.config import settings

ROLES = ("admin", "trader", "viewer")


def hash_password(password: str) -> str:
    """One-way hash. The password cannot be read back."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def password_matches(password: str, password_hash: str) -> bool:
    """True when `password` is the one that was hashed."""
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
    """Encrypt a Dhan client id or access token for the database."""
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str | None) -> str:
    """Decrypt a stored Dhan secret. Empty when nothing was saved."""
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise HTTPException(status_code=500, detail="Stored Dhan credentials could not be decrypted") from exc


def ensure_admin() -> None:
    """Create the first admin from the environment when the table is empty."""
    if db.user_count() or not settings.admin_password:
        return
    db.create_user(settings.admin_username, hash_password(settings.admin_password), "admin")


def current_user(request: Request) -> dict:
    """The account in the session cookie, or 401."""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Login required")
    user = db.get_user(int(user_id))
    if user is None or user["disabled"]:
        raise HTTPException(status_code=401, detail="Login required")
    return user


def require_trader(request: Request) -> dict:
    """A trader. Viewers and admins cannot place or approve orders."""
    user = current_user(request)
    if user["role"] != "trader":
        raise HTTPException(status_code=403, detail="Only a trader can do this")
    return user


def require_admin(request: Request) -> dict:
    """An admin."""
    user = current_user(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only an admin can do this")
    return user


def public_user(user: dict) -> dict:
    """Fields safe to send to the browser. No hash and no Dhan secrets."""
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "disabled": user["disabled"],
        "dhan_saved": user["dhan_saved"],
        "automation_state": user["automation_state"],
        "automation_methods": user["automation_methods"],
    }
