"""
Trade Execution Logs & Analytics API Router.
CRUD operations on recorded trades and portfolio performance analytics.

Endpoints:
- GET    /trades/: List all trades with filtering (symbol, product, asset category, date range).
- POST   /trades/: Manually record a completed trade.
- PUT    /trades/{trade_id}: Update an existing trade entry.
- DELETE /trades/{trade_id}: Delete a trade record.
- GET    /trades/summary: Aggregated P&L metrics, win rate, and capital deployed.
"""

import datetime
from typing import Optional
from fastapi import APIRouter, Query, HTTPException, Body
from sqlalchemy.future import select
from sqlalchemy import func
from pydantic import BaseModel
from app.database import AsyncSessionLocal
from app.models.stock_models import StockTradeLog

router = APIRouter(prefix="/trades", tags=["trades"])


class TradeCreateRequest(BaseModel):
    """
    Manual Trade Creation Payload.
    
    Fields:
    - trade_date (str): 'YYYY-MM-DD'
    - trade_time (str, optional): 'HH:MM:SS'
    - symbol (str): e.g. 'RELIANCE.NS'
    - trade_type (str): 'BUY' or 'SELL'
    - product_type (str, optional): 'INTRADAY' or 'DELIVERY'
    - asset_category (str, optional): 'STOCK', 'GOLD', or 'SILVER'
    - quantity (int): Units
    - price (float): Execution price (₹)
    - stop_loss (float, optional): Stop loss price
    - target_price (float, optional): Target price
    - brokerage (float, optional): Estimated charges
    - realized_pnl (float, optional): Closed P&L if already squared off
    - notes (str, optional): Rationale
    """
    trade_date: str
    trade_time: Optional[str] = None
    symbol: str
    trade_type: str
    product_type: Optional[str] = "INTRADAY"
    asset_category: Optional[str] = "STOCK"
    quantity: int
    price: float
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    brokerage: Optional[float] = 0.0
    realized_pnl: Optional[float] = 0.0
    notes: Optional[str] = None


class TradeUpdateRequest(BaseModel):
    """
    Trade Update Payload.
    """
    price: Optional[float] = None
    quantity: Optional[int] = None
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    realized_pnl: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None


@router.get("/")
async def list_trades(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    symbol: Optional[str] = None,
    trade_type: Optional[str] = None,
    product_type: Optional[str] = None,
    asset_category: Optional[str] = None,
    limit: int = 100,
):
    """
    List all trade logs with optional date range, symbol, and type filters.

    - **Purpose**: Retrieves filtered trade logs for auditing and journaling.
    - **Method**: GET
    - **Query Params**: `start_date`, `end_date`, `symbol`, `trade_type`, `product_type`, `asset_category`, `limit`.
    - **Response**:
      ```json
      {
        "count": 1,
        "trades": [
          {
            "id": 1,
            "trade_date": "2026-09-10",
            "symbol": "RELIANCE.NS",
            "trade_type": "BUY",
            "product_type": "INTRADAY",
            "asset_category": "STOCK",
            "quantity": 10,
            "price": 1290.0,
            "total_value": 12900.0,
            "realized_pnl": 0.0,
            "status": "OPEN"
          }
        ]
      }
      ```
    """
    async with AsyncSessionLocal() as session:
        query = select(StockTradeLog).order_by(StockTradeLog.trade_date.desc(), StockTradeLog.created_at.desc())
        if start_date:
            query = query.where(StockTradeLog.trade_date >= start_date)
        if end_date:
            query = query.where(StockTradeLog.trade_date <= end_date)
        if symbol:
            query = query.where(StockTradeLog.symbol == symbol.strip().upper())
        if trade_type:
            query = query.where(StockTradeLog.trade_type == trade_type.strip().upper())
        if product_type:
            query = query.where(StockTradeLog.product_type == product_type.strip().upper())
        if asset_category:
            query = query.where(StockTradeLog.asset_category == asset_category.strip().upper())
        query = query.limit(limit)
        result = await session.execute(query)
        rows = result.scalars().all()

        data = []
        for r in rows:
            data.append({
                "id": r.id,
                "trade_date": r.trade_date,
                "trade_time": r.trade_time,
                "symbol": r.symbol,
                "trade_type": r.trade_type,
                "product_type": r.product_type,
                "asset_category": r.asset_category,
                "quantity": r.quantity,
                "price": r.price,
                "total_value": round(r.price * r.quantity, 2),
                "stop_loss": r.stop_loss,
                "target_price": r.target_price,
                "brokerage": r.brokerage,
                "realized_pnl": r.realized_pnl,
                "dhan_order_id": r.dhan_order_id,
                "status": r.status,
                "notes": r.notes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })
        return {"count": len(data), "trades": data}


@router.post("/")
async def create_trade(trade: TradeCreateRequest):
    """
    Manually log a buy or sell trade for any date.

    - **Purpose**: Creates an offline / manual trade journal entry.
    - **Method**: POST
    - **Payload**: `TradeCreateRequest` model.
    - **Response**: `{"message": "Trade logged successfully.", "id": 15}`
    """
    async with AsyncSessionLocal() as session:
        t = StockTradeLog(
            trade_date=trade.trade_date,
            trade_time=trade.trade_time or datetime.datetime.now().strftime("%H:%M:%S"),
            symbol=trade.symbol.strip().upper(),
            trade_type=trade.trade_type.strip().upper(),
            product_type=(trade.product_type or "INTRADAY").strip().upper(),
            asset_category=(trade.asset_category or "STOCK").strip().upper(),
            quantity=trade.quantity,
            price=trade.price,
            stop_loss=trade.stop_loss,
            target_price=trade.target_price,
            brokerage=trade.brokerage or 0.0,
            realized_pnl=trade.realized_pnl or 0.0,
            status="EXECUTED",
            notes=trade.notes,
        )
        session.add(t)
        await session.commit()
        await session.refresh(t)
        return {"message": "Trade logged successfully.", "id": t.id}


@router.put("/{trade_id}")
async def update_trade(trade_id: int, updates: TradeUpdateRequest):
    """
    Update an existing trade log entry.

    - **Purpose**: Modifies price, quantity, stop-loss, status, or realized P&L.
    - **Method**: PUT
    - **Path Params**: `trade_id` (int)
    - **Payload**: `TradeUpdateRequest` model.
    """
    async with AsyncSessionLocal() as session:
        t = await session.get(StockTradeLog, trade_id)
        if not t:
            raise HTTPException(status_code=404, detail=f"Trade ID {trade_id} not found.")
        if updates.price is not None:
            t.price = updates.price
        if updates.quantity is not None:
            t.quantity = updates.quantity
        if updates.stop_loss is not None:
            t.stop_loss = updates.stop_loss
        if updates.target_price is not None:
            t.target_price = updates.target_price
        if updates.realized_pnl is not None:
            t.realized_pnl = updates.realized_pnl
        if updates.status is not None:
            t.status = updates.status
        if updates.notes is not None:
            t.notes = updates.notes
        await session.commit()
        return {"message": "Trade updated.", "id": trade_id}


@router.delete("/{trade_id}")
async def delete_trade(trade_id: int):
    """
    Delete a trade log entry.

    - **Purpose**: Removes a recorded trade from the database.
    - **Method**: DELETE
    - **Path Params**: `trade_id` (int)
    """
    async with AsyncSessionLocal() as session:
        t = await session.get(StockTradeLog, trade_id)
        if not t:
            raise HTTPException(status_code=404, detail=f"Trade ID {trade_id} not found.")
        await session.delete(t)
        await session.commit()
        return {"message": f"Trade ID {trade_id} deleted."}


@router.get("/summary")
async def trade_summary():
    """
    P&L summary: total capital deployed, realized P&L, win rate, and trade counts.

    - **Purpose**: Aggregates top-line statistics for dashboard scorecards.
    - **Method**: GET
    - **Response**:
      ```json
      {
        "total_trades": 18,
        "buy_count": 12,
        "sell_count": 6,
        "total_capital_deployed_inr": 245000.0,
        "realized_pnl_inr": 14250.0,
        "win_rate_pct": 72.2
      }
      ```
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(StockTradeLog))
        all_trades = result.scalars().all()

        total_trades = len(all_trades)
        buys = [t for t in all_trades if t.trade_type == "BUY"]
        sells = [t for t in all_trades if t.trade_type == "SELL"]
        total_capital = sum(t.price * t.quantity for t in buys)
        realized_pnl = sum(t.realized_pnl for t in all_trades)
        winning_trades = [t for t in all_trades if t.realized_pnl > 0]
        closed_trades = [t for t in all_trades if t.status in ("SQUARED_OFF", "EXECUTED") and t.realized_pnl != 0]
        win_rate = (len(winning_trades) / len(closed_trades) * 100) if closed_trades else 0.0

        return {
            "total_trades": total_trades,
            "buy_count": len(buys),
            "sell_count": len(sells),
            "total_capital_deployed_inr": round(total_capital, 2),
            "realized_pnl_inr": round(realized_pnl, 2),
            "win_rate_pct": round(win_rate, 2),
        }
