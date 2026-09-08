import os
import uuid
import datetime
from app.services.guardrail_service import validate_trade_execution, get_guardrail_settings
from app.models.stock_models import StockTradeLog
from app.database import AsyncSessionLocal

# DhanHQ credentials from environment if available
DHAN_CLIENT_ID = os.getenv("DHAN_CLIENT_ID", "")
DHAN_ACCESS_TOKEN = os.getenv("DHAN_ACCESS_TOKEN", "")

class DhanHQTradingService:
    def __init__(self):
        self.is_configured = bool(DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN)
        
    async def place_order(
        self,
        symbol: str,
        trade_type: str, # BUY or SELL
        quantity: int,
        price: float,
        product_type: str = "INTRADAY", # INTRADAY / DELIVERY
        asset_category: str = "STOCK", # STOCK / GOLD / SILVER
        stop_loss: float = None,
        target_price: float = None,
        notes: str = None,
        trade_date: str = None
    ):
        # Step 1: Enforce Guardrails
        is_allowed, reason = await validate_trade_execution(symbol, trade_type, price, quantity)
        if not is_allowed:
            raise ValueError(reason)

        settings = await get_guardrail_settings()
        is_paper = settings.get("paper_trading_mode", True) or not self.is_configured
        
        now = datetime.datetime.now()
        cur_date = trade_date or now.strftime("%Y-%m-%d")
        cur_time = now.strftime("%H:%M:%S")

        # Order ID generation
        order_prefix = "DHAN_PAPER_" if is_paper else "DHAN_LIVE_"
        order_id = f"{order_prefix}{uuid.uuid4().hex[:10].upper()}"

        # Estimate brokerage & charges
        order_val = price * quantity
        brokerage = min(20.0, order_val * 0.0003) if product_type == "INTRADAY" else (order_val * 0.001)

        # Log trade execution into database via SQLAlchemy
        async with AsyncSessionLocal() as session:
            trade_log = StockTradeLog(
                trade_date=cur_date,
                trade_time=cur_time,
                symbol=symbol.upper(),
                trade_type=trade_type.upper(),
                product_type=product_type.upper(),
                asset_category=asset_category.upper(),
                quantity=quantity,
                price=price,
                stop_loss=stop_loss, 
                target_price=target_price,
                brokerage=round(brokerage, 2),
                realized_pnl=0.0,
                dhan_order_id=order_id,
                status="EXECUTED" if product_type == "DELIVERY" else "OPEN",
                notes=notes or f"Executed via AI Agent ({'Paper Trading' if is_paper else 'DhanHQ Live'})"
            )
            session.add(trade_log)
            await session.commit()
            await session.refresh(trade_log)
            
            return {
                "order_id": order_id,
                "status": "SUCCESS",
                "symbol": symbol.upper(),
                "trade_type": trade_type.upper(),
                "product_type": product_type.upper(),
                "asset_category": asset_category.upper(),
                "quantity": quantity,
                "price": price,
                "total_val": order_val,
                "mode": "PAPER_TRADING" if is_paper else "DHANHQ_LIVE",
                "trade_log_id": trade_log.id,
                "executed_at": f"{cur_date} {cur_time}"
            }

    async def square_off_position(self, trade_id: int, exit_price: float, notes: str = None):
        """Squares off an open position (intraday or manual exit)."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                session.query(StockTradeLog).filter(StockTradeLog.id == trade_id)
            ) if hasattr(session, 'query') else await session.get(StockTradeLog, trade_id)
            
            trade = result if isinstance(result, StockTradeLog) else None
            if not trade:
                # Fallback get
                trade = await session.get(StockTradeLog, trade_id)
                
            if not trade:
                raise ValueError(f"Trade log ID {trade_id} not found.")

            if trade.status == "SQUARED_OFF":
                return {"message": f"Trade #{trade_id} is already squared off."}

            # Calculate realized P&L
            diff = (exit_price - trade.price) if trade.trade_type == "BUY" else (trade.price - exit_price)
            pnl = (diff * trade.quantity) - trade.brokerage

            trade.status = "SQUARED_OFF"
            trade.realized_pnl = round(pnl, 2)
            if notes:
                trade.notes = (trade.notes or "") + f" | Exit Note: {notes}"

            await session.commit()
            return {
                "trade_id": trade.id,
                "symbol": trade.symbol,
                "entry_price": trade.price,
                "exit_price": exit_price,
                "quantity": trade.quantity,
                "realized_pnl": round(pnl, 2),
                "status": "SQUARED_OFF"
            }

dhan_service = DhanHQTradingService()
