"""
Trading guardrails — the master kill-switch, paper-vs-live mode, and the
order-value / daily-loss limits. Moved from app/services/guardrail_service.py
with one addition: the daily-loss limit is now actually enforced (it was
previously stored and displayed but never checked before an order).

app.services.dhan_service.place_order() calls validate_trade_execution()
before every single order, paper or live — this is the one and only gate
an order has to pass, regardless of what asked for it (a manual API call,
the harness, or the trade-recommendation agent if it's later wired up to
auto-execute).
"""

import datetime
from sqlalchemy.future import select
from sqlalchemy import func

from app.db.base import AsyncSessionLocal
from app.db.models import TradingGuardrailSettings
from app.db.models_trading import Trade

DEFAULTS = {
    "is_trading_enabled": False,
    "paper_trading_mode": True,
    "max_order_value_inr": 100000.0,
    "max_daily_loss_inr": 25000.0,
    "auto_intraday_exit_time": "15:15",
}


async def get_guardrail_settings() -> dict:
    """Fetches guardrail settings from DB, creating the single settings row
    with defaults on first run."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(TradingGuardrailSettings).filter_by(id=1))
        settings = result.scalars().first()
        if not settings:
            settings = TradingGuardrailSettings(id=1, **DEFAULTS)
            session.add(settings)
            await session.commit()
            await session.refresh(settings)

        return {
            "is_trading_enabled": settings.is_trading_enabled,
            "paper_trading_mode": settings.paper_trading_mode,
            "max_order_value_inr": settings.max_order_value_inr,
            "max_daily_loss_inr": settings.max_daily_loss_inr,
            "auto_intraday_exit_time": settings.auto_intraday_exit_time,
            "updated_at": settings.updated_at.isoformat() if settings.updated_at else datetime.datetime.utcnow().isoformat(),
        }


async def update_guardrail_settings(
    is_trading_enabled: bool = None,
    paper_trading_mode: bool = None,
    max_order_value_inr: float = None,
) -> dict:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(TradingGuardrailSettings).filter_by(id=1))
        settings = result.scalars().first()
        if not settings:
            settings = TradingGuardrailSettings(id=1)
            session.add(settings)

        if is_trading_enabled is not None:
            settings.is_trading_enabled = is_trading_enabled
        if paper_trading_mode is not None:
            settings.paper_trading_mode = paper_trading_mode
        if max_order_value_inr is not None:
            settings.max_order_value_inr = max_order_value_inr

        settings.updated_at = datetime.datetime.utcnow()
        await session.commit()

    return await get_guardrail_settings()


async def get_today_realized_pnl() -> float:
    """Sums realized_pnl across today's squared-off trades — what the
    daily-loss check below is measured against."""
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.coalesce(func.sum(Trade.realized_pnl), 0.0)).where(
                func.date(Trade.created_at) == today_str,
                Trade.status == "CLOSED",
            )
        )
        return float(result.scalar() or 0.0)


async def validate_trade_execution(symbol: str, trade_type: str, price: float, quantity: int) -> tuple[bool, str]:
    """The single gate every order passes through. Returns (is_allowed, reason)."""
    settings = await get_guardrail_settings()

    if not settings["is_trading_enabled"]:
        return False, "TRADING IS DISABLED: Master Kill-Switch is ACTIVE. Trading is currently turned OFF from the system guardrails."

    total_val = price * quantity
    if total_val > settings["max_order_value_inr"]:
        return False, (
            f"ORDER VALUE EXCEEDED: Total order value (₹{total_val:,.2f}) exceeds max single order "
            f"guardrail limit (₹{settings['max_order_value_inr']:,.2f})."
        )

    today_pnl = await get_today_realized_pnl()
    if today_pnl <= -abs(settings["max_daily_loss_inr"]):
        return False, (
            f"DAILY LOSS LIMIT BREACHED: Today's realized P&L (₹{today_pnl:,.2f}) has hit the daily "
            f"loss guardrail (₹{settings['max_daily_loss_inr']:,.2f}). No new trades until this is reset."
        )

    return True, "Guardrails Passed"
