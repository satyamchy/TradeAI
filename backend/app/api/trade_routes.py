# """Trade journal CRUD and P&L summary APIs."""

# from typing import Optional

# from fastapi import APIRouter, HTTPException

# from app.schemas.trading import TradeCreateRequest, TradeUpdateRequest
# from app.services.trade_service import (
#     create_trade,
#     delete_trade,
#     get_trade_summary,
#     list_trades,
#     update_trade,
# )

# router = APIRouter(prefix="/trades", tags=["trades"])


# @router.get("/")
# async def get_trades(
#     start_date: Optional[str] = None,
#     end_date: Optional[str] = None,
#     symbol: Optional[str] = None,
#     trade_type: Optional[str] = None,
#     product_type: Optional[str] = None,
#     asset_category: Optional[str] = None,
#     limit: int = 100,
# ):
#     try:
#         return await list_trades(
#             start_date=start_date,
#             end_date=end_date,
#             symbol=symbol,
#             trade_type=trade_type,
#             product_type=product_type,
#             asset_category=asset_category,
#             limit=limit,
#         )
#     except ValueError as exc:
#         raise HTTPException(status_code=400, detail=str(exc)) from exc


# @router.post("/")
# async def add_trade(trade: TradeCreateRequest):
#     try:
#         return await create_trade(trade)
#     except ValueError as exc:
#         raise HTTPException(status_code=400, detail=str(exc)) from exc


# @router.get("/summary")
# async def trade_summary():
#     try:
#         return await get_trade_summary()
#     except ValueError as exc:
#         raise HTTPException(status_code=500, detail=str(exc)) from exc


# @router.put("/{trade_id}")
# async def edit_trade(trade_id: int, updates: TradeUpdateRequest):
#     try:
#         return await update_trade(trade_id, updates)
#     except ValueError as exc:
#         status = 404 if "not found" in str(exc).lower() else 400
#         raise HTTPException(status_code=status, detail=str(exc)) from exc


# @router.delete("/{trade_id}")
# async def remove_trade(trade_id: int):
#     try:
#         return await delete_trade(trade_id)
#     except ValueError as exc:
#         status = 404 if "not found" in str(exc).lower() else 400
#         raise HTTPException(status_code=status, detail=str(exc)) from exc
