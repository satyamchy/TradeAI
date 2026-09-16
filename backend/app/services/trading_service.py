"""Simple trading service shared by frontend and AI endpoints."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.db.models import Order, Position, Trade
from app.guardrails.trading_guardrails import validate_trade_execution
from app.integrations.dhan.client import (
    BUY,
    DELIVERY,
    INTRADAY,
    LIMIT,
    MARKET,
    NSE_EQ,
    SELL,
    DhanAPIError,
    cancel_order_raw,
    get_fund_limits_raw,
    get_holdings_raw,
    get_order_by_id_raw,
    get_order_list_raw,
    get_positions_raw,
    is_dhan_configured,
    place_order_raw,
    refresh_security_master,
    resolve_security_id,
)


def _order_dict(row: Order) -> dict:
    return {
        "id": row.id,
        "symbol": row.symbol,
        "security_id": row.security_id,
        "side": row.side,
        "quantity": row.quantity,
        "order_type": row.order_type,
        "product_type": row.product_type,
        "price": row.requested_price,
        "broker_order_id": row.broker_order_id,
        "status": row.status,
        "mode": row.mode,
        "source": row.source,
        "confirmation_id": row.confirmation_id,
        "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _trade_dict(row: Trade) -> dict:
    return {
        "id": row.id,
        "order_id": row.order_id,
        "broker_order_id": row.broker_order_id,
        "symbol": row.symbol,
        "side": row.side,
        "quantity": row.quantity,
        "price": row.price,
        "product_type": row.product_type,
        "realized_pnl": row.realized_pnl,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _position_dict(row: Position) -> dict:
    market_value = row.quantity * (row.last_price or row.average_price)
    return {
        "id": row.id,
        "symbol": row.symbol,
        "security_id": row.security_id,
        "product_type": row.product_type,
        "quantity": row.quantity,
        "average_price": row.average_price,
        "last_price": row.last_price,
        "market_value": round(market_value, 2),
        "unrealized_pnl": round(row.unrealized_pnl, 2),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _extract(response: Any, *keys: str) -> Any:
    if not isinstance(response, dict):
        return None
    data = response.get("data")
    if isinstance(data, dict):
        for key in keys:
            if data.get(key) is not None:
                return data[key]
    for key in keys:
        if response.get(key) is not None:
            return response[key]
    return None


async def _sync_position(
    session,
    symbol: str,
    security_id: Optional[str],
    side: str,
    quantity: int,
    price: float,
    product_type: str,
) -> Position:
    position = (
        await session.execute(select(Position).where(Position.symbol == symbol))
    ).scalar_one_or_none()

    signed_qty = quantity if side == "BUY" else -quantity
    if not position:
        position = Position(
            symbol=symbol,
            security_id=security_id,
            product_type=product_type,
            quantity=max(signed_qty, 0),
            average_price=price,
            last_price=price,
            unrealized_pnl=0.0,
        )
        session.add(position)
        return position

    old_qty = position.quantity
    new_qty = old_qty + signed_qty

    if signed_qty > 0:
        total_cost = old_qty * position.average_price + quantity * price
        position.average_price = total_cost / new_qty if new_qty else 0.0
    elif new_qty <= 0:
        position.average_price = 0.0

    position.quantity = max(new_qty, 0)
    position.security_id = security_id or position.security_id
    position.product_type = product_type
    position.last_price = price
    position.unrealized_pnl = round(
        (position.last_price - position.average_price) * position.quantity,
        2,
    )
    return position


async def execute_order(
    symbol: str,
    side: str,
    quantity: int,
    order_type: str = "MARKET",
    product_type: str = "INTRADAY",
    price: float = 0.0,
    source: str = "frontend",
    notes: Optional[str] = None,
    force_live: Optional[bool] = None,
) -> dict:
    symbol = symbol.strip().upper().replace(".NS", "")
    side = side.upper()
    order_type = order_type.upper()
    product_type = product_type.upper()

    if side not in {"BUY", "SELL"}:
        raise ValueError("side must be BUY or SELL")
    if order_type not in {"MARKET", "LIMIT"}:
        raise ValueError("order_type must be MARKET or LIMIT")
    if product_type not in {"INTRADAY", "DELIVERY"}:
        raise ValueError("product_type must be INTRADAY or DELIVERY")
    if quantity <= 0:
        raise ValueError("quantity must be greater than 0")
    if price < 0:
        raise ValueError("price cannot be negative")
    if order_type == "LIMIT" and price <= 0:
        raise ValueError("price is required for LIMIT orders")

    # MARKET orders use the latest quote for risk/value checks.
    if order_type == "MARKET" and price <= 0:
        from app.services.market_data_service import fetch_stock_market_data
        quote = (await fetch_stock_market_data(f"{symbol}.NS", period="5d", interval="1d")).get("quote", {})
        price = float(quote.get("current_price") or 0)
        if price <= 0:
            raise ValueError(f"Could not determine a current price for {symbol}")

    allowed, reason = await validate_trade_execution(
        symbol=symbol,
        trade_type=side,
        price=price,
        quantity=quantity,
    )
    if not allowed:
        raise ValueError(reason)

    from app.guardrails.trading_guardrails import get_guardrail_settings
    guardrails = await get_guardrail_settings()
    live = bool(force_live) if force_live is not None else not guardrails["paper_trading_mode"]

    security_id = await resolve_security_id(symbol) if live else None
    if is_dhan_configured() is False and force_live:
        raise ValueError("DhanHQ is not configured for live trading")

    if live and not is_dhan_configured():
        raise ValueError("DhanHQ credentials are not configured")

    broker_order_id = None
    broker_response = None
    status = "PENDING"
    execution_price = price

    if live:
        if not security_id:
            raise ValueError(f"Could not resolve Dhan security_id for {symbol}")

        broker_response = await place_order_raw(
            security_id=security_id,
            exchange_segment=NSE_EQ,
            transaction_type=BUY if side == "BUY" else SELL,
            quantity=quantity,
            order_type=MARKET if order_type == "MARKET" else LIMIT,
            product_type=INTRADAY if product_type == "INTRADAY" else DELIVERY,
            price=0 if order_type == "MARKET" else price,
        )
        broker_order_id = str(_extract(broker_response, "orderId", "order_id") or "") or None
        status = str(_extract(broker_response, "orderStatus", "status") or "PENDING").upper()

        if broker_order_id:
            try:
                details = await get_order_by_id_raw(broker_order_id)
                execution_price = float(
                    _extract(details, "averageTradedPrice", "tradedPrice", "price") or price
                )
                status = str(
                    _extract(details, "orderStatus", "status") or status
                ).upper()
            except Exception:
                pass
    else:
        broker_order_id = f"PAPER-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{symbol}"
        status = "TRADED"
        execution_price = price

    async with AsyncSessionLocal() as session:
        order = Order(
            symbol=symbol,
            security_id=security_id,
            side=side,
            quantity=quantity,
            order_type=order_type,
            product_type=product_type,
            requested_price=price,
            broker_order_id=broker_order_id,
            status=status,
            mode="LIVE" if live else "PAPER",
            source=source,
            notes=notes,
        )
        session.add(order)
        await session.flush()

        trade = None
        if status in {"TRADED", "EXECUTED", "COMPLETE"}:
            trade = Trade(
                order_id=order.id,
                broker_order_id=broker_order_id,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=execution_price,
                product_type=product_type,
                status="OPEN",
            )
            session.add(trade)
            await session.flush()
            await _sync_position(
                session,
                symbol,
                security_id,
                side,
                quantity,
                execution_price,
                product_type,
            )

        await session.commit()
        await session.refresh(order)

        return {
            "order": _order_dict(order),
            "trade": _trade_dict(trade) if trade else None,
            "broker_response": broker_response,
        }


async def create_pending_ai_order(
    symbol: str,
    side: str,
    quantity: int,
    product_type: str,
    order_type: str,
    price: float,
    notes: Optional[str],
) -> dict:
    confirmation_id = f"AI-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    async with AsyncSessionLocal() as session:
        order = Order(
            symbol=symbol.strip().upper().replace(".NS", ""),
            side=side,
            quantity=quantity,
            order_type=order_type,
            product_type=product_type,
            requested_price=price,
            status="PENDING_CONFIRMATION",
            mode="PENDING",
            source="llm",
            confirmation_id=confirmation_id,
            notes=notes,
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return {"confirmation_id": confirmation_id, "order": _order_dict(order)}


async def confirm_ai_order(order_id: int) -> dict:
    async with AsyncSessionLocal() as session:
        order = await session.get(Order, order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        if order.status != "PENDING_CONFIRMATION":
            raise ValueError(f"Order {order_id} is not awaiting confirmation")

        symbol = order.symbol
        side = order.side
        quantity = order.quantity
        order_type = order.order_type
        product_type = order.product_type
        price = order.requested_price
        notes = order.notes

    result = await execute_order(
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_type=order_type,
        product_type=product_type,
        price=price,
        source="llm",
        notes=notes,
    )
    return {"confirmed_order_id": order_id, **result}


async def list_orders() -> list[dict]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(select(Order).order_by(Order.created_at.desc()))
        ).scalars().all()
        return [_order_dict(row) for row in rows]


async def get_order(order_id: int) -> dict:
    async with AsyncSessionLocal() as session:
        row = await session.get(Order, order_id)
        if not row:
            raise ValueError(f"Order {order_id} not found")
        return _order_dict(row)


async def cancel_order(order_id: int) -> dict:
    async with AsyncSessionLocal() as session:
        row = await session.get(Order, order_id)
        if not row:
            raise ValueError(f"Order {order_id} not found")
        if row.broker_order_id and row.mode == "LIVE":
            await cancel_order_raw(row.broker_order_id)
        row.status = "CANCELLED"
        await session.commit()
        return _order_dict(row)


async def list_trades() -> list[dict]:
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(Trade).order_by(Trade.created_at.desc()))).scalars().all()
        return [_trade_dict(row) for row in rows]


async def list_positions() -> list[dict]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Position).where(Position.quantity > 0).order_by(Position.symbol)
            )
        ).scalars().all()
        return [_position_dict(row) for row in rows]


async def get_holdings() -> dict:
    if not is_dhan_configured():
        return {"mode": "paper", "holdings": []}
    raw = await get_holdings_raw()
    return {"mode": "live", "holdings": raw if isinstance(raw, list) else raw.get("data", raw)}


async def get_positions() -> dict:
    if not is_dhan_configured():
        return {"mode": "paper", "positions": await list_positions()}
    raw = await get_positions_raw()
    broker_positions = raw if isinstance(raw, list) else raw.get("data", raw)
    return {"mode": "live", "positions": broker_positions}


async def get_funds() -> dict:
    if not is_dhan_configured():
        return {"mode": "paper", "available_margin": 0.0}
    raw = await get_fund_limits_raw()
    return {"mode": "live", "funds": raw}


async def _sync_filled_order(session, row: Order, broker_data: Any) -> None:
    status = str(_extract(broker_data, "orderStatus", "status") or row.status).upper()
    row.status = status
    if status not in {"TRADED", "EXECUTED", "COMPLETE"}:
        return

    existing = (
        await session.execute(select(Trade).where(Trade.order_id == row.id))
    ).scalar_one_or_none()
    if existing:
        return

    filled_price = float(
        _extract(broker_data, "averageTradedPrice", "tradedPrice", "price")
        or row.requested_price
        or 0
    )
    filled_qty = int(
        _extract(broker_data, "tradedQty", "filledQuantity", "quantity")
        or row.quantity
    )
    trade = Trade(
        order_id=row.id,
        broker_order_id=row.broker_order_id,
        symbol=row.symbol,
        side=row.side,
        quantity=filled_qty,
        price=filled_price,
        product_type=row.product_type,
        status="OPEN",
    )
    session.add(trade)
    await _sync_position(
        session,
        row.symbol,
        row.security_id,
        row.side,
        filled_qty,
        filled_price,
        row.product_type,
    )


async def refresh_order_from_broker(order_id: int) -> dict:
    async with AsyncSessionLocal() as session:
        row = await session.get(Order, order_id)
        if not row:
            raise ValueError(f"Order {order_id} not found")
        if not row.broker_order_id:
            return _order_dict(row)
        raw = await get_order_by_id_raw(row.broker_order_id)
        await _sync_filled_order(session, row, raw)
        await session.commit()
        return _order_dict(row)


async def list_instruments() -> dict:
    if not is_dhan_configured():
        return {"mode": "paper", "count": 0, "instruments": []}
    count = await refresh_security_master()
    from app.integrations.dhan.client import get_security_master
    return {"mode": "live", "count": count, "instruments": get_security_master()}
