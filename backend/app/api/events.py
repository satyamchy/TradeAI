"""Event log reads. Writes happen in the routes that change an order."""

from fastapi import APIRouter, HTTPException, Query, Request

from app import db
from app.auth import current_user

router = APIRouter(prefix="/events", tags=["events"])


@router.get("")
def get_events(request: Request, user_id: int | None = None, limit: int = Query(default=100, ge=1, le=200)):
    """Newest order events for the logged-in user.

    An admin may pass `user_id` to read another account. 401 when logged out.
    """
    user = current_user(request)
    target = user["id"]
    if user_id is not None and user_id != user["id"]:
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Only an admin can read another user's log")
        target = user_id
    rows = db.list_events(target, limit)
    return {"count": len(rows), "events": rows}
