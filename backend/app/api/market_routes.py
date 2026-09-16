"""Small market data API."""

from fastapi import APIRouter, HTTPException, Query

from app.services.company_resolver import resolve_ticker_symbol
from app.services.market_data_service import fetch_stock_market_data
from app.services.trading_service import list_instruments

router = APIRouter(prefix="/market", tags=["Maarket"])


@router.get("/quote/{symbol}")
async def quote(symbol: str):
    try:
        ticker = resolve_ticker_symbol(symbol)
        data = await fetch_stock_market_data(ticker, period="5d", interval="1d")
        return data["quote"]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/history/{symbol}")
async def history(
    symbol: str,
    period: str = Query(default="1mo"),
    interval: str = Query(default="1d"),
):
    try:
        ticker = resolve_ticker_symbol(symbol)
        data = await fetch_stock_market_data(ticker, period=period, interval=interval)
        return {
            "symbol": ticker,
            "period": period,
            "interval": interval,
            "history": data["history"],
            "intraday": data["intraday_candles"],
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/instruments")
async def instruments():
    try:
        return await list_instruments()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
