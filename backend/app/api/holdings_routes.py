# """
# DhanHQ Holdings API Router.
# Dedicated solely to GET queries for Dhan account holdings and individual stock holding metrics.
# Separated from execution/mutation routes (POST, PUT, DELETE, PATCH).

# Endpoints:
# - GET /holdings           : Retrieves all holdings, summary P&L, delivery and T1 quantities.
# - GET /holdings/{symbol}  : Retrieves detailed holding data for a specific stock or ISIN.
# """

# from fastapi import APIRouter, HTTPException
# from app.services.dhan_service import get_holdings, get_holding_detail

# router = APIRouter(prefix="/holdings", tags=["holdings"])


# @router.get("", summary="Get Dhan Demat Holdings")
# @router.get("/", include_in_schema=False)
# async def get_all_holdings():
#     """
#     Fetches all holdings bought/sold in previous trading sessions from Dhan account.
#     Retrieves delivered (DP) and T1 settlement quantities, average buy price,
#     current market price (LTP), invested value, current value, and profit/loss.
    
#     URL and credentials are read dynamically from .env:
#     - DHAN_HOLDINGS_URL (defaults to https://api.dhan.co/v2/holdings)
#     - DHAN_CLIENT_ID
#     - DHAN_ACCESS_TOKEN
#     """
#     try:
#         return await get_holdings()
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Failed to fetch holdings: {str(e)}")



# @router.get("/{symbol_or_isin}", summary="Get Single Stock Holding Detail")
# async def get_single_stock_holding(symbol_or_isin: str):
#     """
#     Retrieves detailed holding metrics for a single stock by symbol (e.g. RELIANCE) or ISIN.
#     """
#     try:
#         return await get_holding_detail(symbol_or_isin)
#     except ValueError as err:
#         raise HTTPException(status_code=404, detail=str(err))
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error fetching holding detail: {str(e)}")




