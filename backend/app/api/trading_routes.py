from fastapi import APIRouter, HTTPException, Body
from app.services.guardrail_service import get_guardrail_settings, update_guardrail_settings
from app.services.dhan_service import dhan_service
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/trading", tags=["trading"])

class OrderRequest(BaseModel):
    symbol: str
    trade_type: str # BUY / SELL
    quantity: int
    price: float
    product_type: Optional[str] = "INTRADAY" # INTRADAY / DELIVERY
    asset_category: Optional[str] = "STOCK" # STOCK / GOLD / SILVER
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    notes: Optional[str] = None

class SquareOffRequest(BaseModel):
    exit_price: float
    notes: Optional[str] = None

@router.get("/guardrails/status")
async def guardrails_status():
    """Returns safety guardrails and Master Kill-Switch status."""
    return await get_guardrail_settings()

@router.post("/guardrails/toggle")
async def toggle_guardrails(is_trading_enabled: bool = Body(..., embed=True)):
    """Enables or disables live trading instantly (Master Kill-Switch)."""
    return await update_guardrail_settings(is_trading_enabled=is_trading_enabled)

@router.post("/orders")
async def place_order(order: OrderRequest):
    """Submits buy/sell order via DhanHQ API or Paper engine after Guardrail checks."""
    try:
        res = await dhan_service.place_order(
            symbol=order.symbol,
            trade_type=order.trade_type,
            quantity=order.quantity,
            price=order.price,
            product_type=order.product_type,
            asset_category=order.asset_category,
            stop_loss=order.stop_loss,
            target_price=order.target_price,
            notes=order.notes
        )
        return res
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))

@router.post("/square-off/{trade_id}")
async def square_off(trade_id: int, req: SquareOffRequest):
    """Squares off open position (intraday auto-exit or manual user exit)."""
    try:
        return await dhan_service.square_off_position(
            trade_id=trade_id,
            exit_price=req.exit_price,
            notes=req.notes
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
