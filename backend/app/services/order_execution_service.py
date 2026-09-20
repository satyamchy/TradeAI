import logging
from app.integrations.dhan.client import get_dhan_client
from app.services.trading_risk_service import run_risk_checks
from app.services.position_monitor import schedule_position_monitor

logger = logging.getLogger(__name__)


async def place_dhan_buy_order(security_id: str, exchange: str, quantity: int, price_cap: float, trade_type: str) -> str:
    dhan = get_dhan_client()

    exchange_segment = dhan.NSE if exchange.upper() == "NSE" else dhan.BSE
    product_type = dhan.INTRA if trade_type == "INTRADAY" else dhan.CNC

    resp = dhan.place_order(
        security_id=security_id,
        exchange_segment=exchange_segment,
        transaction_type=dhan.BUY,
        quantity=quantity,
        order_type=dhan.LIMIT,      # LIMIT, not MARKET — we have an explicit price cap
        product_type=product_type,
        price=price_cap,
    )

    if resp.get("status") == "failure" or "orderId" not in resp.get("data", resp):
        raise RuntimeError(f"Dhan order placement failed: {resp}")

    data = resp.get("data", resp)
    order_id = data.get("orderId") or data.get("order_id")
    if not order_id:
        raise RuntimeError(f"No order ID in Dhan response: {resp}")

    logger.info("Placed Dhan order %s for security %s, qty %s, cap %s, type %s", order_id, security_id, quantity, price_cap, trade_type)
    return order_id


async def execute_recommendation(instrument_security_id: str, exchange: str, recommendation: dict, quantity: int, symbol: str) -> dict:
    if not recommendation["buy_flag"]:
        return {"attempted": False, "executed": False, "reason": "buy_flag is false", "order_id": None}

    risk_result = await run_risk_checks(
        entry_price_cap=recommendation["entry_price_cap"],
        quantity=quantity,
        trade_type=recommendation["trade_type"],
        security_id=instrument_security_id,
    )
    if not risk_result.passed:
        logger.warning("Risk check blocked order for %s: %s", instrument_security_id, risk_result.reason)
        return {"attempted": True, "executed": False, "reason": risk_result.reason, "order_id": None}

    try:
        order_id = await place_dhan_buy_order(
            security_id=instrument_security_id,
            exchange=exchange,
            quantity=quantity,
            price_cap=recommendation["entry_price_cap"],
            trade_type=recommendation["trade_type"],
        )
    except Exception as e:
        logger.error("Order placement failed for %s: %s", instrument_security_id, e, exc_info=True)
        return {"attempted": True, "executed": False, "reason": f"Order placement failed: {e}", "order_id": None}

    schedule_position_monitor(
        order_id=order_id,
        security_id=instrument_security_id,
        symbol=symbol,
        trade_type=recommendation["trade_type"],
        stop_loss=recommendation["stop_loss"],
        target_price=recommendation["target_price"],
    )

    return {"attempted": True, "executed": True, "reason": "Order placed", "order_id": order_id}