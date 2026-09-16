"""Local trade-journal CRUD and summary functions."""

import datetime
from typing import Optional

from sqlalchemy.future import select

from app.db.base import AsyncSessionLocal
from app.db.models import StockTradeLog


async def list_trades(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    symbol: Optional[str] = None,
    trade_type: Optional[str] = None,
    product_type: Optional[str] = None,
    asset_category: Optional[str] = None,
    limit: int = 100,
):
    try:
        limit = max(1, min(limit, 500))
        async with AsyncSessionLocal() as session:
            query = select(StockTradeLog).order_by(
                StockTradeLog.trade_date.desc(),
                StockTradeLog.created_at.desc(),
            )
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

            rows = (await session.execute(query.limit(limit))).scalars().all()

            return {
                "count": len(rows),
                "trades": [_trade_to_dict(row) for row in rows],
            }
    except Exception as exc:
        raise ValueError(f"Failed to list trades: {exc}") from exc


def _trade_to_dict(trade: StockTradeLog) -> dict:
    return {
        "id": trade.id,
        "trade_date": trade.trade_date,
        "trade_time": trade.trade_time,
        "symbol": trade.symbol,
        "trade_type": trade.trade_type,
        "product_type": trade.product_type,
        "asset_category": trade.asset_category,
        "quantity": trade.quantity,
        "price": trade.price,
        "total_value": round(trade.price * trade.quantity, 2),
        "stop_loss": trade.stop_loss,
        "target_price": trade.target_price,
        "brokerage": trade.brokerage,
        "realized_pnl": trade.realized_pnl,
        "dhan_order_id": trade.dhan_order_id,
        "status": trade.status,
        "notes": trade.notes,
        "created_at": trade.created_at.isoformat() if trade.created_at else None,
    }


async def create_trade(trade):
    try:
        async with AsyncSessionLocal() as session:
            row = StockTradeLog(
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
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return {"message": "Trade logged successfully.", "id": row.id}
    except Exception as exc:
        raise ValueError(f"Failed to create trade: {exc}") from exc


async def get_trade_summary():
    try:
        async with AsyncSessionLocal() as session:
            trades = (await session.execute(select(StockTradeLog))).scalars().all()

        buys = [t for t in trades if t.trade_type == "BUY"]
        sells = [t for t in trades if t.trade_type == "SELL"]
        closed = [
            t for t in trades
            if t.status in {"SQUARED_OFF", "EXECUTED"} and t.realized_pnl != 0
        ]
        wins = [t for t in closed if t.realized_pnl > 0]

        return {
            "total_trades": len(trades),
            "buy_count": len(buys),
            "sell_count": len(sells),
            "total_capital_deployed_inr": round(sum(t.price * t.quantity for t in buys), 2),
            "realized_pnl_inr": round(sum(t.realized_pnl for t in trades), 2),
            "win_rate_pct": round((len(wins) / len(closed)) * 100, 2) if closed else 0.0,
        }
    except Exception as exc:
        raise ValueError(f"Failed to calculate trade summary: {exc}") from exc


async def update_trade(trade_id: int, updates):
    try:
        async with AsyncSessionLocal() as session:
            trade = await session.get(StockTradeLog, trade_id)
            if not trade:
                raise ValueError(f"Trade ID {trade_id} not found.")

            for field in (
                "price",
                "quantity",
                "stop_loss",
                "target_price",
                "realized_pnl",
                "status",
                "notes",
            ):
                value = getattr(updates, field)
                if value is not None:
                    setattr(trade, field, value)

            await session.commit()
            return {"message": "Trade updated.", "id": trade_id}
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Failed to update trade: {exc}") from exc


async def delete_trade(trade_id: int):
    try:
        async with AsyncSessionLocal() as session:
            trade = await session.get(StockTradeLog, trade_id)
            if not trade:
                raise ValueError(f"Trade ID {trade_id} not found.")
            await session.delete(trade)
            await session.commit()
            return {"message": f"Trade ID {trade_id} deleted."}
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Failed to delete trade: {exc}") from exc
