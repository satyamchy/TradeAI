"""Login cookie. Passwords are checked here and nowhere else."""

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.auth import current_user, password_matches, public_user
from app import db

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    """Account name and password. There is no public signup."""

    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


@router.post("/login")
def login(body: LoginRequest, request: Request):
    """Set the session cookie. 401 when the name or password is wrong."""
    user = db.get_user_by_username(body.username.strip())
    if user is None or user["disabled"] or not password_matches(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Wrong username or password")
    request.session["user_id"] = user["id"]
    return {"user": public_user(user)}


@router.post("/logout")
def logout(request: Request, response: Response):
    """Clear the session cookie."""
    request.session.clear()
    return {"ok": True}


@router.get("/session")
def session(request: Request):
    """The logged-in user, or 401."""
    return {"user": public_user(current_user(request))}
