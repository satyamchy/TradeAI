import os
import datetime
from sqlalchemy.future import select
from app.database import AsyncSessionLocal
from app.models.stock_models import TradingGuardrailSettings

# InMemory cache fallback
_guardrail_cache = {
    "is_trading_enabled": False,
    "paper_trading_mode": True,
    "max_order_value_inr": 100000.0,
    "max_daily_loss_inr": 25000.0,
    "auto_intraday_exit_time": "15:15"
}

async def get_guardrail_settings():
    """Fetches guardrail settings from DB or returns defaults."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(TradingGuardrailSettings).filter_by(id=1))
        settings = result.scalars().first()
        if not settings:
            settings = TradingGuardrailSettings(
                id=1,
                is_trading_enabled=False,
                paper_trading_mode=True,
                max_order_value_inr=100000.0,
                max_daily_loss_inr=25000.0,
                auto_intraday_exit_time="15:15"
            )
            session.add(settings)
            await session.commit()
            await session.refresh(settings)
        
        _guardrail_cache["is_trading_enabled"] = settings.is_trading_enabled
        _guardrail_cache["paper_trading_mode"] = settings.paper_trading_mode
        _guardrail_cache["max_order_value_inr"] = settings.max_order_value_inr
        _guardrail_cache["max_daily_loss_inr"] = settings.max_daily_loss_inr
        _guardrail_cache["auto_intraday_exit_time"] = settings.auto_intraday_exit_time

        return {
            "is_trading_enabled": settings.is_trading_enabled,
            "paper_trading_mode": settings.paper_trading_mode,
            "max_order_value_inr": settings.max_order_value_inr,
            "max_daily_loss_inr": settings.max_daily_loss_inr,
            "auto_intraday_exit_time": settings.auto_intraday_exit_time,
            "updated_at": settings.updated_at.isoformat() if settings.updated_at else datetime.datetime.utcnow().isoformat()
        }

async def update_guardrail_settings(is_trading_enabled: bool = None, paper_trading_mode: bool = None, max_order_value_inr: float = None):
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
        await session.refresh(settings)
        
        _guardrail_cache["is_trading_enabled"] = settings.is_trading_enabled
        _guardrail_cache["paper_trading_mode"] = settings.paper_trading_mode
        _guardrail_cache["max_order_value_inr"] = settings.max_order_value_inr
        
        return await get_guardrail_settings()

async def validate_trade_execution(symbol: str, trade_type: str, price: float, quantity: int):
    """
    Validates if a trade can be executed according to safety guardrails and master kill-switch.
    Returns (is_valid: bool, reason: str).
    """
    settings = await get_guardrail_settings()
    
    if not settings["is_trading_enabled"]:
        return False, "TRADING IS DISABLED: Master Kill-Switch is ACTIVE. Trading is currently turned OFF from the system guardrails."
    
    total_val = price * quantity
    if total_val > settings["max_order_value_inr"]:
        return False, f"ORDER VALUE EXCEEDED: Total order value (₹{total_val:,.2f}) exceeds max single order guardrail limit (₹{settings['max_order_value_inr']:,.2f})."
        
    return True, "Guardrails Passed"
