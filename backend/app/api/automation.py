"""Turn intraday entries on and off, and read what the loop just did.

These routes do not place orders except `square-off-open-positions`,
which flattens intraday positions the loop already knows about.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.trading.automation_runner import automation_runner

router = APIRouter(prefix="/automation", tags=["automation"])


class EnableAutomationRequest(BaseModel):
    """Methods the loop may open. Existing positions are still managed either way."""

    methods: list[str] = Field(min_length=1)


class AutomationSettingsPatch(BaseModel):
    """In-memory limit changes. Omitted fields stay as they are. Percents are numbers, not fractions, except the cash ratios."""

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


@router.get("/status")
async def get_automation_status():
    """Whether entries are on, which methods, and if the NSE session is open."""
    return await automation_runner.status()


@router.post("/enable")
async def enable_automation(body: EnableAutomationRequest):
    """Allow new entries for `intraday_long`, `intraday_short`, or both.

    Live entries are refused unless the process was started with
    TRADING_MODE=live. The body cannot switch a paper process into live.
    Enabling outside the session does not place an order; the loop waits.
    """
    try:
        automation_runner.enable(body.methods)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await automation_runner.status()


@router.post("/disable")
async def disable_automation():
    """Stop new entries. Open positions stay until an exit rule or square-off."""
    automation_runner.disable()
    return await automation_runner.status()


@router.post("/square-off-open-positions")
async def square_off_open_positions():
    """Close every open intraday position at the latest price the cycle can see."""
    try:
        return await automation_runner.square_off_open_positions()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/recent-cycles")
async def get_recent_cycles():
    """The last 50 cycle snapshots, oldest first."""
    cycles = automation_runner.recent_cycles()
    return {"count": len(cycles), "cycles": cycles}


@router.get("/settings")
async def get_automation_settings():
    """The limits the next cycle will use. Cash ratios are fractions. Take-profit and stop-loss are percents."""
    return _settings_payload()


@router.patch("/settings")
async def patch_automation_settings(body: AutomationSettingsPatch):
    """Change limits for later cycles. This does not rewrite the environment file."""
    try:
        automation_runner.replace_limits(body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _settings_payload()
