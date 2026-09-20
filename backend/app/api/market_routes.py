# """Small market data API."""

# from fastapi import APIRouter, HTTPException, Query

# from app.services.company_resolver import CompanyResolutionError, resolve_ticker_symbol
# from app.services.market_data_service import fetch_stock_market_data 
# # fetch_stock_intraday_data
# from app.services.trading_service import list_instruments
# from app.services.company_resolver import resolve_company_v2, CompanyResolutionError
# from app.schemas.market import ResolveResponse

# router = APIRouter(prefix="/market", tags=["Maarket"])


# @router.get("/quote/{symbol}")
# async def quote(symbol: str):
#     try:
#         ticker = resolve_ticker_symbol(symbol)
#     except CompanyResolutionError as exc:
#         # 404: this is a "we don't know what you meant" case, not a server failure
#         raise HTTPException(status_code=404, detail=str(exc)) from exc
        
#     try:
#         data = await fetch_stock_market_data(ticker, period="5d", interval="1d")
#     except Exception as exc:
#         # 502: resolution succeeded, but the upstream data fetch itself failed
#         raise HTTPException(status_code=502, detail=f"Failed to fetch data for {ticker}: {exc}") from exc

#     return data

# @router.get("/history/{symbol}")
# async def history(
#     symbol: str,
#     period: str = Query(default="1mo"),
#     interval: str = Query(default="1d"),
#     include_intraday: bool = Query(default=False)
# ):
#     try:
#         ticker = resolve_ticker_symbol(symbol)
#         data = await fetch_stock_market_data(ticker, period=period, interval=interval, include_fundamentals=False,)
#         response = {
#             "symbol": ticker,
#             "period": period,
#             "interval": interval,
#             "history": data["history"],
#             # "intraday": data["intraday_candles"],
#         }
#         # if include_intraday:
#         #     response["intraday"] = await fetch_stock_intraday_data(ticker)

#         return response
#     except Exception as exc:
#         raise HTTPException(status_code=502, detail=str(exc)) from exc


# # @router.get("/intraday/{symbol}")
# # async def intraday(
# #     symbol: str,
# #     interval: str = Query( default="15m", description="Intraday interval: 1m, 2m, 5m, 15m, 30m, 60m, 90m", ),
# #     period: str = Query( default="5d", description="Intraday period. yfinance limits intraday history.",),
# # ):
# #     """
# #     Return intraday OHLCV candles.
# #     """

# #     try:
# #         ticker = resolve_ticker_symbol(symbol)

# #         candles = await fetch_stock_intraday_data(
# #             ticker=ticker,
# #             period=period,
# #             interval=interval,
# #         )

# #         return {
# #             "symbol": ticker,
# #             "period": period,
# #             "interval": interval,
# #             "candles": candles,
# #         }
# #     except Exception as exc:
# #             raise HTTPException(status_code=502, detail=str(exc)) from exc
    

# @router.get("/instruments")
# async def instruments():
#     try:
#         return await list_instruments()
#     except Exception as exc:
#         raise HTTPException(status_code=502, detail=str(exc)) from exc

# # app/api/routes/market.py  (add route)

# @router.get("/resolve", response_model=ResolveResponse)
# async def resolve(query: str = Query(..., min_length=1)):
#     try:
#         result = await resolve_company_v2(query)
#     except CompanyResolutionError as exc:
#         raise HTTPException(status_code=404, detail=str(exc)) from exc

#     if result["confidence"] == "ambiguous":
#         return ResolveResponse(resolved=None, needs_disambiguation=True, candidates=result["candidates"])

#     return ResolveResponse(resolved=result["instrument"], needs_disambiguation=False)

# # @router.post("/analyze")
# # async def analyze_stock(query: str):
# #     result = await resolve_company_v2(query, allow_llm_disambiguation=True)
# #     if result["confidence"] == "ambiguous":
# #         return {"needs_disambiguation": True, "candidates": result["candidates"]}

# #     instrument = result["instrument"]
# #     market_data = await fetch_stock_market_data(instrument.symbol)
# #     analysis = await llm_analyze(instrument, market_data)  # your existing LLM analysis step

# #     return {
# #         "instrument": instrument,      # <-- frontend stores this whole object
# #         "market_data": market_data,
# #         "analysis": analysis,
# #     }
