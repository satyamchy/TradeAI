"""Admin-only account management."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app import db
from app.auth import ROLES, hash_password, public_user, require_admin

router = APIRouter(prefix="/users", tags=["users"])


class CreateUserRequest(BaseModel):
    """A new account. The password is hashed before it is stored."""

    username: str = Field(min_length=1)
    password: str = Field(min_length=8)
    role: str


class UpdateUserRequest(BaseModel):
    """Role or disabled flag. Omitted fields stay as they are."""

    role: str | None = None
    disabled: bool | None = None


@router.get("")
def get_users(request: Request):
    """Every account, without passwords or Dhan secrets. Admin only. 403 otherwise."""
    require_admin(request)
    return {"users": db.list_users()}


@router.post("")
def post_user(body: CreateUserRequest, request: Request):
    """Create an account. Admin only. 400 for a duplicate name or a bad role."""
    require_admin(request)
    if body.role not in ROLES:
        raise HTTPException(status_code=400, detail="role must be admin, trader, or viewer")
    if db.get_user_by_username(body.username.strip()):
        raise HTTPException(status_code=400, detail="That username already exists")
    user = db.create_user(body.username.strip(), hash_password(body.password), body.role)
    return public_user(user)


@router.patch("/{user_id}")
def patch_user(user_id: int, body: UpdateUserRequest, request: Request):
    """Change role or disable an account. Admin only. 404 when the id is unknown."""
    require_admin(request)
    if body.role is not None and body.role not in ROLES:
        raise HTTPException(status_code=400, detail="role must be admin, trader, or viewer")
    previous = db.get_user(user_id)
    if previous is None:
        raise HTTPException(status_code=404, detail="User not found")
    losing_admin = previous["role"] == "admin" and not previous["disabled"] and (
        body.disabled is True or (body.role is not None and body.role != "admin")
    )
    if losing_admin:
        others = [
            row
            for row in db.list_users()
            if row["role"] == "admin" and not row["disabled"] and row["id"] != user_id
        ]
        if not others:
            raise HTTPException(status_code=400, detail="The last admin cannot be disabled or demoted")
    leaving_trader = previous["role"] == "trader" and (
        body.disabled is True or (body.role is not None and body.role != "trader")
    )
    if leaving_trader:
        db.set_automation(user_id, "exits_only", previous["automation_methods"] or "[]")
    user = db.update_user(user_id, role=body.role, disabled=body.disabled)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return public_user(user)
