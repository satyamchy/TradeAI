"""Public trading API."""

from fastapi import APIRouter, HTTPException

from app.schemas.trading import OrderRequest
from app.services.trading_service import (
    cancel_order,
    execute_order,
    get_funds,
    get_holdings,
    get_order,
    get_positions,
    list_orders,
    list_positions,
    list_trades,
    refresh_order_from_broker,
)

router = APIRouter(prefix="/trading", tags=["Trading"])


@router.post("/orders")
async def create_order(request: OrderRequest):
    try:
        return await execute_order(**request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/orders")
async def orders():
    return {"count": len(rows := await list_orders()), "orders": rows}


@router.get("/orders/{order_id}")
async def order_detail(order_id: int, refresh: bool = True):
    try:
        if refresh:
            try:
                return await refresh_order_from_broker(order_id)
            except Exception:
                pass
        return await get_order(order_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/orders/{order_id}")
async def delete_order(order_id: int):
    try:
        return await cancel_order(order_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/trades")
async def trades():
    rows = await list_trades()
    return {"count": len(rows), "trades": rows}


@router.get("/holdings")
async def holdings():
    try:
        return await get_holdings()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/positions")
async def positions():
    try:
        return await get_positions()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/funds")
async def funds():
    try:
        return await get_funds()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
