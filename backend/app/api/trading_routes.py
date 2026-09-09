"""
Trading Execution & Guardrails API Router.
Handles live and paper order routing with DhanHQ broker integration and Master Kill-Switch safety.

Endpoints:
- GET  /trading/guardrails/status: Returns status of kill-switch, paper mode, and order limits.
- POST /trading/guardrails/toggle: Enables or disables live trading instantly.
- POST /trading/orders: Submits buy/sell orders through safety guardrails.
- POST /trading/square-off/{trade_id}: Squares off open position calculating realized P&L.
"""

from fastapi import APIRouter, HTTPException, Body
from app.services.guardrail_service import get_guardrail_settings, update_guardrail_settings
from app.services.dhan_service import dhan_service
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/trading", tags=["trading"])


class OrderRequest(BaseModel):
    """
    Order Execution Payload.
    
    Fields:
    - symbol (str): e.g. 'RELIANCE.NS', 'GOLDBEES.NS'
    - trade_type (str): 'BUY' or 'SELL'
    - quantity (int): Number of units / shares
    - price (float): Limit or execution price (₹)
    - product_type (str, optional): 'INTRADAY' or 'DELIVERY' (default 'INTRADAY')
    - asset_category (str, optional): 'STOCK', 'GOLD', or 'SILVER' (default 'STOCK')
    - stop_loss (float, optional): Stop-loss trigger price
    - target_price (float, optional): Profit target price
    - notes (str, optional): Execution comments or AI rationale
    """
    symbol: str
    trade_type: str
    quantity: int
    price: float
    product_type: Optional[str] = "INTRADAY"
    asset_category: Optional[str] = "STOCK"
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    notes: Optional[str] = None


class SquareOffRequest(BaseModel):
    """
    Square-Off Exit Payload.
    
    Fields:
    - exit_price (float): Price at which position was squared off (₹)
    - notes (str, optional): Exit rationale or notes
    """
    exit_price: float
    notes: Optional[str] = None


@router.get("/guardrails/status")
async def guardrails_status():
    """
    Returns safety guardrails and Master Kill-Switch status.

    - **Purpose**: Checks whether automated/manual live trading is enabled and gets limits.
    - **Method**: GET
    - **Response**:
      ```json
      {
        "is_trading_enabled": false,
        "paper_trading_mode": true,
        "max_order_value_inr": 100000.0,
        "max_daily_loss_inr": 25000.0,
        "auto_intraday_exit_time": "15:15",
        "updated_at": "2026-09-10T01:00:00"
      }
      ```
    """
    return await get_guardrail_settings()


@router.post("/guardrails/toggle")
async def toggle_guardrails(is_trading_enabled: bool = Body(..., embed=True)):
    """
    Enables or disables live trading instantly (Master Kill-Switch).

    - **Purpose**: Emergency halt / resume of order execution across the system.
    - **Method**: POST
    - **Payload**:
      ```json
      {
        "is_trading_enabled": true
      }
      ```
    - **Response**: Updated guardrail settings object.
    """
    return await update_guardrail_settings(is_trading_enabled=is_trading_enabled)


@router.post("/orders")
async def place_order(order: OrderRequest):
    """
    Submits buy/sell order via DhanHQ API or Paper engine after Guardrail checks.

    - **Purpose**: Validates limits and executes trades.
    - **Method**: POST
    - **Payload**: `OrderRequest` model.
    - **Response**:
      ```json
      {
        "order_id": "DHAN_PAPER_A1B2C3D4",
        "status": "SUCCESS",
        "symbol": "TCS.NS",
        "trade_type": "BUY",
        "product_type": "INTRADAY",
        "quantity": 10,
        "price": 2250.0,
        "total_val": 22500.0,
        "mode": "PAPER_TRADING",
        "trade_log_id": 14,
        "executed_at": "2026-09-10 09:30:00"
      }
      ```
    """
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
    """
    Squares off open position (intraday auto-exit or manual user exit).

    - **Purpose**: Realizes profit/loss, deducts brokerage, and updates trade status to `SQUARED_OFF`.
    - **Method**: POST
    - **Path Params**: `trade_id` (int)
    - **Payload**: `SquareOffRequest` model.
    - **Response**:
      ```json
      {
        "trade_id": 14,
        "symbol": "TCS.NS",
        "entry_price": 2250.0,
        "exit_price": 2275.0,
        "quantity": 10,
        "realized_pnl": 230.0,
        "status": "SQUARED_OFF"
      }
      ```
    """
    try:
        return await dhan_service.square_off_position(
            trade_id=trade_id,
            exit_price=req.exit_price,
            notes=req.notes
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
