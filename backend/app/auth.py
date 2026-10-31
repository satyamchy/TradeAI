"""Compatibility facade for authentication imports not yet migrated."""

from app.shared.security import (
    ROLES,
    current_user,
    decrypt_secret,
    encrypt_secret,
    ensure_admin,
    hash_password,
    password_matches,
    public_user,
    require_admin,
    require_trader,
)

__all__ = [
    "ROLES",
    "current_user",
    "decrypt_secret",
    "encrypt_secret",
    "ensure_admin",
    "hash_password",
    "password_matches",
    "public_user",
    "require_admin",
    "require_trader",
]
