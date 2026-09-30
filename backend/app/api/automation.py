"""Per-trader automation switch and the shared risk limits.

Enable and disable do not place orders. Square-off closes that trader's
intraday positions only.
"""

import json
from collections import deque

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app import db
from app.auth import current_user, require_admin, require_trader
from app.broker.trading_gateway import gateway_for_user
from app.trading.automation_runner import ALLOWED_METHODS, CYCLE_HISTORY, automation_runner
from app.trading.intraday_cycle import run_intraday_cycle
from app.trading.nse_session import is_nse_cash_session_open, is_past_entry_cutoff, is_square_off_time, now_ist
from app.trading.pending import set_user_automation

router = APIRouter(prefix="/automation", tags=["automation"])


class EnableAutomationRequest(BaseModel):
    """Methods this trader may open. Existing positions are still managed either way."""

    methods: list[str] = Field(min_length=1)


class AutomationSettingsPatch(BaseModel):
    """Shared limits. Omitted fields stay as they are. Admin only."""

    max_positions: int | None = Field(default=None, ge=1)
    capital_per_trade_pct: float | None = None
    cash_reserve_pct: float | None = None
    take_profit_pct: float | None = None
    stop_loss_pct: float | None = None
    max_daily_loss_inr: float | None = None
    screener_limit: int | None = Field(default=None, ge=1)
    cycle_interval_seconds: int | None = Field(default=None, ge=30)


def _settings_payload() -> dict:
    limits = automation_runner.limits
    return {
        "max_positions": limits.max_positions,
        "capital_per_trade_pct": limits.capital_per_trade_pct,
        "cash_reserve_pct": limits.cash_reserve_pct,
        "take_profit_pct": limits.take_profit_pct,
        "stop_loss_pct": limits.stop_loss_pct,
        "max_daily_loss_inr": limits.max_daily_loss_inr,
        "screener_limit": limits.screener_limit,
        "cycle_interval_seconds": limits.cycle_interval_seconds,
    }


def _view(user: dict, position_count: int | None) -> dict:
    moment = now_ist()
    session_open = is_nse_cash_session_open(moment)
    past_cutoff = is_past_entry_cutoff(moment)
    square_off_due = session_open and is_square_off_time(moment)
    entries_on = user["automation_state"] == "entries"
    if not entries_on:
        next_action = "managing_exits_only" if user["automation_state"] == "exits_only" else "disabled"
    elif not session_open:
        next_action = "waiting_for_session"
    elif square_off_due:
        next_action = "square_off"
    elif past_cutoff:
        next_action = "managing_exits_only"
    else:
        next_action = "running_entries"
    cycles = automation_runner.user_cycles.get(user["id"], [])
    return {
        "enabled": entries_on,
        "automation_state": user["automation_state"],
        "mode": gateway_for_user(user).mode,
        "methods": json.loads(user["automation_methods"] or "[]"),
        "market_open": session_open,
        "past_entry_cutoff": past_cutoff,
        "square_off_due": square_off_due,
        "next_action": next_action,
        "last_error": automation_runner.user_errors.get(user["id"]),
        "open_position_count": position_count,
        "cycle_count": len(cycles),
    }


async def _status(user: dict) -> dict:
    try:
        positions = await gateway_for_user(user).get_open_positions()
        count = len([row for row in positions if row.get("product_type", "INTRADAY") == "INTRADAY"])
    except Exception as exc:
        automation_runner.user_errors[user["id"]] = str(exc)
        count = None
    fresh = db.get_user(user["id"]) or user
    return _view(fresh, count)


@router.get("/status")
async def get_automation_status(request: Request):
    """Whether this user's entries are on, and if the NSE session is open. 401 when logged out."""
    return await _status(current_user(request))


@router.post("/enable")
async def enable_automation(body: EnableAutomationRequest, request: Request):
    """Allow new intraday entries for this trader.

    403 unless the caller is a trader. 400 when a method name is unknown.
    Enabling outside the session does not place an order.
    """
    user = require_trader(request)
    unknown = [method for method in body.methods if method not in ALLOWED_METHODS]
    if unknown:
        raise HTTPException(status_code=400, detail="methods must include intraday_long, intraday_short, or both")
    methods = list(dict.fromkeys(body.methods))
    set_user_automation(user, "entries", methods)
    return await _status(user)


@router.post("/disable")
async def disable_automation(request: Request):
    """Stop new entries. Open intraday positions are still flattened by the exit rules. 403 for non-traders."""
    user = require_trader(request)
    set_user_automation(user, "exits_only", json.loads(user["automation_methods"] or "[]"))
    return await _status(user)


@router.post("/square-off-open-positions")
async def square_off_open_positions(request: Request):
    """Close this trader's open intraday positions now. 403 for non-traders. Delivery holdings are left alone."""
    user = require_trader(request)
    methods = json.loads(user["automation_methods"] or "[]")
    try:
        snapshot = await run_intraday_cycle(
            gateway_for_user(user),
            entries_enabled=False,
            methods=methods,
            limits=automation_runner.limits,
            force_square_off=True,
        )
    except Exception as exc:
        db.add_event(user["id"], "square_off", "failed", detail=str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    automation_runner.user_cycles.setdefault(user["id"], deque(maxlen=CYCLE_HISTORY)).append(snapshot)
    db.add_event(user["id"], "square_off", "placed", detail=f"{len(snapshot.get('exits', []))} exits")
    return snapshot


@router.get("/recent-cycles")
def get_recent_cycles(request: Request):
    """The last cycle snapshots for this user, oldest first. 401 when logged out."""
    user = current_user(request)
    cycles = list(automation_runner.user_cycles.get(user["id"], []))
    return {"count": len(cycles), "cycles": cycles}


@router.get("/settings")
def get_automation_settings(request: Request):
    """The shared limits the next cycle will use. 401 when logged out."""
    current_user(request)
    return _settings_payload()


@router.patch("/settings")
def patch_automation_settings(body: AutomationSettingsPatch, request: Request):
    """Change the shared limits. Admin only. 400 when a value is out of range. 403 otherwise."""
    admin = require_admin(request)
    try:
        automation_runner.replace_limits(body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.add_event(admin["id"], "settings", "placed", detail="shared limits updated")
    return _settings_payload()
