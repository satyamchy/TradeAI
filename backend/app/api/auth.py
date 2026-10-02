"""Login cookie. Passwords are checked here and nowhere else."""

import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.auth import current_user, password_matches, public_user
from app import db

_failures: dict[str, list[float]] = {}

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    """Account name and password. There is no public signup."""

    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


@router.post("/login")
def login(body: LoginRequest, request: Request):
    """Set the session cookie. 401 when the name or password is wrong."""
    username = body.username.strip()
    if _locked(username):
        raise HTTPException(status_code=429, detail="Too many login attempts. Wait a minute and try again.")
    user = db.get_user_by_username(username)
    if user is None or user["disabled"] or not password_matches(body.password, user["password_hash"]):
        _record_failure(username)
        raise HTTPException(status_code=401, detail="Wrong username or password")
    _failures.pop(username, None)
    request.session["user_id"] = user["id"]
    return {"user": public_user(user)}


@router.post("/logout")
def logout(request: Request, response: Response):
    """Clear the session cookie."""
    request.session.clear()
    return {"ok": True}


def _locked(username: str) -> bool:
    now = time.time()
    recent = [stamp for stamp in _failures.get(username, []) if now - stamp < 60]
    _failures[username] = recent
    return len(recent) >= 8


def _record_failure(username: str) -> None:
    now = time.time()
    recent = [stamp for stamp in _failures.get(username, []) if now - stamp < 60]
    recent.append(now)
    _failures[username] = recent


@router.get("/session")
def session(request: Request):
    """The logged-in user, or 401."""
    return {"user": public_user(current_user(request))}
