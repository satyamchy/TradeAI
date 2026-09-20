"""
Monitors open positions for exit conditions:
- INTRADAY: forced square-off at 15:15 IST same day, or earlier if target/SL hit.
- DELIVERY: checked periodically; sold when target or stop-loss is hit (no forced exit).
"""

import logging
import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.services.market_data_service import fetch_stock_market_data
from app.integrations.dhan.client import get_dhan_client

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")


# async def _sell_position(order_id: str, security_id: str, reason: str):
#     logger.info("Exiting position %s (security %s): %s", order_id, security_id, reason)
#     # TODO: real Dhan sell call
#     # await dhan_client.place_order(security_id=security_id, transaction_type="SELL", ...)

async def _sell_position(order_id: str, security_id: str, reason: str, exchange: str = "NSE", product_type: str = "INTRA"):
    logger.info("Exiting position %s (security %s): %s", order_id, security_id, reason)
    dhan = get_dhan_client()

    positions_resp = dhan.get_positions()
    positions = positions_resp.get("data", positions_resp) if isinstance(positions_resp, dict) else positions_resp
    position = next((p for p in positions if str(p.get("securityId")) == str(security_id)), None)

    if not position or float(position.get("netQty", 0)) == 0:
        logger.warning("No open quantity found for security %s — nothing to sell", security_id)
        return

    qty = int(abs(float(position["netQty"])))
    exchange_segment = dhan.NSE if exchange.upper() == "NSE" else dhan.BSE
    prod_type = dhan.INTRA if product_type == "INTRA" else dhan.CNC

    resp = dhan.place_order(
        security_id=security_id,
        exchange_segment=exchange_segment,
        transaction_type=dhan.SELL,
        quantity=qty,
        order_type=dhan.MARKET,   # exits should fill immediately, not sit as a limit order
        product_type=prod_type,
        price=0,
    )

    if resp.get("status") == "failure":
        logger.error("SELL order failed for %s: %s", security_id, resp)
        raise RuntimeError(f"Sell failed: {resp}")

    logger.info("Sell order placed for %s: %s", security_id, resp)

async def _check_exit_condition(order_id: str, security_id: str, symbol: str, stop_loss: float, target_price: float):
    try:
        data = await fetch_stock_market_data(symbol)
        current_price = data["quote"]["current_price"]
    except Exception as e:
        logger.warning("Could not fetch price for position check on %s: %s", symbol, e)
        return

    if current_price is None:
        return
    if stop_loss and current_price <= stop_loss:
        await _sell_position(order_id, security_id, f"Stop-loss hit at {current_price}")
        scheduler.remove_job(f"monitor_{order_id}")
    elif target_price and current_price >= target_price:
        await _sell_position(order_id, security_id, f"Target hit at {current_price}")
        scheduler.remove_job(f"monitor_{order_id}")



async def _force_square_off(order_id: str, security_id: str):
    await _sell_position(order_id, security_id, "Intraday forced square-off (EOD)")
    job_id = f"monitor_{order_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)


def schedule_position_monitor(order_id: str, security_id: str, trade_type: str, stop_loss: float, target_price: float, symbol: str = None):
    symbol = symbol or security_id  # pass the yfinance-compatible symbol through if available

    scheduler.add_job(
        _check_exit_condition,
        trigger=IntervalTrigger(minutes=5),
        args=[order_id, security_id, symbol, stop_loss, target_price],
        id=f"monitor_{order_id}",
        replace_existing=True,
    )

    if trade_type == "INTRADAY":
        today = datetime.datetime.now().date()
        square_off_time = datetime.datetime.combine(today, datetime.time(15, 15))
        scheduler.add_job(
            _force_square_off,
            trigger=DateTrigger(run_date=square_off_time),
            args=[order_id, security_id],
            id=f"squareoff_{order_id}",
            replace_existing=True,
        )