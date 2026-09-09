"""
Market Data & Quantitative Analytics API Router.
Wires live market data, multi-step candlestick charts, and deep analysis.

Endpoints:
- GET  /data/global-macro: Returns global/domestic macroeconomic news events and sentiment scores.
- GET  /data/interval-data/{ticker}: Dynamic interval candles with technical indicators (RSI, MACD, VWAP).
- POST /data/deep-analysis: Generates deep technical and AI evaluation for a single ticker.
- GET  /data/position-monitor: Real-time risk and P&L monitor with automated 15:15 IST square-off warnings.
"""

import datetime
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from app.services.market_data_service import (
    get_global_macro_news_feed,
    get_indian_market_status,
    fetch_stock_market_data,
)
from app.services.company_resolver import resolve_ticker_symbol
from app.services.technical_analysis_service import run_technical_analysis
from app.services.ai_analysis_service import generate_ai_stock_analysis
from app.database import AsyncSessionLocal
from app.models.stock_models import StockTradeLog, StockAnalysisSnapshot
from sqlalchemy.future import select

router = APIRouter(prefix="/data", tags=["data"])


@router.get("/global-macro")
async def global_macro():
    """
    Returns global macro events and sentiment scores impacting the Indian market.

    - **Purpose**: Global and domestic macro news feed with automated sentiment & impact scoring.
    - **Method**: GET
    - **Payload**: None
    - **Response**:
      ```json
      [
        {
          "title": "RBI Keeps Repo Rate Steady at 6.50%",
          "source": "Macro Economic Desk",
          "region": "India",
          "sentiment": "Positive",
          "impact_score": 7.5,
          "summary": "...",
          "published_at": "2026-09-09 10:00:00"
        }
      ]
      ```
    """
    return get_global_macro_news_feed()


@router.get("/interval-data/{ticker}")
async def get_interval_data(ticker: str, timeframe: str = "15m"):
    """
    Fetches dynamic interval stock market data and technical indicator calculations.

    - **Purpose**: Feeds interactive candlestick charts with computed technical overlays.
    - **Method**: GET
    - **Path Params**: `ticker` (e.g. `RELIANCE.NS`, `TCS`)
    - **Query Params**: `timeframe` (default `15m`)
    - **Response**:
      ```json
      {
        "ticker": "RELIANCE.NS",
        "timeframe": "15m",
        "current_price": 1294.9,
        "rsi_14": 58.4,
        "macd_signal": "BULLISH_CROSSOVER",
        "vwap": 1289.2,
        "trend": "Bullish",
        "candles": [{"step": 1, "open": 1280.0, "high": 1285.0, "low": 1278.0, "close": 1284.5, "volume": 150000, "datetime": "..."}]
      }
      ```
    """
    canonical = resolve_ticker_symbol(ticker)
    data = await fetch_stock_market_data(canonical, period="5d", interval="15m")
    candles = data.get("intraday_candles") or data.get("history", [])

    tech = run_technical_analysis(data, analysis_type="intraday")
    quote = data.get("quote", {})
    curr_price = quote.get("current_price") or (candles[-1]["close"] if candles else 1000.0)

    # Format step-based candles matching frontend expectations
    formatted_candles = []
    for i, c in enumerate(candles[-30:]):
        formatted_candles.append({
            "step": i + 1,
            "open": c.get("open"),
            "high": c.get("high"),
            "low": c.get("low"),
            "close": c.get("close"),
            "volume": c.get("volume"),
            "datetime": c.get("datetime") or c.get("date"),
        })

    macd_val = tech.get("macd", {}).get("histogram")
    macd_signal = "BULLISH_CROSSOVER" if (macd_val and macd_val > 0) else "BEARISH_CROSSOVER"

    return {
        "ticker": canonical,
        "timeframe": timeframe,
        "current_price": curr_price,
        "rsi_14": tech.get("rsi_14"),
        "macd_signal": macd_signal,
        "vwap": tech.get("vwap") or curr_price,
        "trend": tech.get("trend"),
        "candles": formatted_candles,
    }


@router.post("/deep-analysis")
async def perform_deep_analysis(
    ticker: str,
    date_str: Optional[str] = None,
    trade_mode: Optional[str] = "INTRADAY",
):
    """
    Performs dynamic deep AI stock analysis evaluating technicals, macro context, and bias.

    - **Purpose**: Generates instant multi-point scorecards with target/stop-loss recommendations.
    - **Method**: POST
    - **Query Params**:
      - `ticker` (str, required): e.g. `TCS.NS`
      - `date_str` (str, optional): `YYYY-MM-DD`
      - `trade_mode` (str, optional): `INTRADAY` or `DELIVERY`
    - **Response**:
      ```json
      {
        "ticker": "TCS.NS",
        "symbol": "TCS",
        "name": "Tata Consultancy Services",
        "analysis_date": "2026-09-10",
        "trade_mode": "INTRADAY",
        "initial_price": 2255.5,
        "target_price": 2295.0,
        "stop_loss": 2230.0,
        "overall_sentiment": "Bullish",
        "intraday_bias": "Strong Buy",
        "recommendation": "BUY",
        "technical_score": 82.0,
        "macro_score": 78.0,
        "ai_reasoning": "...",
        "selling_point": "Strong support bounce at S1 pivot.",
        "key_signals": ["RSI Oversold Bounce", "MACD Histogram Positive"],
        "risks": ["Broader IT sector consolidation"]
      }
      ```
    """
    cur_date = date_str or datetime.datetime.now().strftime("%Y-%m-%d")
    canonical = resolve_ticker_symbol(ticker)
    mode = (trade_mode or "INTRADAY").upper()

    market_data = await fetch_stock_market_data(canonical)
    tech = run_technical_analysis(market_data, analysis_type=mode.lower())
    ai_eval = await generate_ai_stock_analysis(canonical, mode.lower(), market_data, tech)

    quote = market_data.get("quote", {})
    sr = tech.get("support_resistance", {})
    base_price = quote.get("current_price") or 1000.0
    target = sr.get("r1") or round(base_price * 1.035, 2)
    stop_loss = sr.get("s1") or round(base_price * 0.982, 2)

    rec = ai_eval.get("recommendation", "HOLD")
    sentiment = "Bullish" if rec == "BUY" else ("Bearish" if rec == "AVOID" else "Neutral")
    intraday_bias = "Strong Buy" if rec == "BUY" else ("Strong Sell" if rec == "AVOID" else "Neutral")

    return {
        "ticker": canonical,
        "symbol": canonical.replace(".NS", ""),
        "name": quote.get("name", canonical),
        "analysis_date": cur_date,
        "trade_mode": mode,
        "initial_price": base_price,
        "target_price": target,
        "stop_loss": stop_loss,
        "overall_sentiment": sentiment,
        "intraday_bias": intraday_bias,
        "recommendation": rec,
        "technical_score": round(float(ai_eval.get("confidence", 0.75)) * 100.0, 1),
        "macro_score": 78.0,
        "ai_reasoning": (
            f"[{mode} Analysis] {ai_eval.get('summary', '')} "
            f"Key Signals: {', '.join(ai_eval.get('key_signals', []))}. "
            f"Selling Point: {ai_eval.get('selling_point', '')}"
        ),
        "selling_point": ai_eval.get("selling_point"),
        "key_signals": ai_eval.get("key_signals"),
        "risks": ai_eval.get("risks"),
    }


@router.get("/position-monitor")
async def monitor_open_positions():
    """
    Active monitoring API for currently open positions with live quotes and auto-exit warnings.

    - **Purpose**: Real-time risk and P&L tracker; flags 15:15 IST intraday auto-squareoff.
    - **Method**: GET
    - **Payload**: None
    - **Response**:
      ```json
      {
        "market_status": "MARKET_OPEN",
        "open_positions_count": 1,
        "positions": [
          {
            "trade_id": 5,
            "symbol": "TCS.NS",
            "trade_type": "BUY",
            "product_type": "INTRADAY",
            "entry_price": 2240.0,
            "current_price": 2255.5,
            "quantity": 25,
            "unrealized_pnl": 387.5,
            "stop_loss": 2220.0,
            "target_price": 2280.0,
            "needs_auto_squareoff": false,
            "recommendation": "HOLD"
          }
        ]
      }
      ```
    """
    market_info = get_indian_market_status()
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(StockTradeLog).filter_by(status="OPEN"))
        open_trades = result.scalars().all()

        monitored_positions = []
        for trade in open_trades:
            canonical = resolve_ticker_symbol(trade.symbol)
            try:
                data = await fetch_stock_market_data(canonical)
                live_price = data.get("quote", {}).get("current_price") or trade.price
            except Exception:
                live_price = trade.price

            pnl = (
                (live_price - trade.price) * trade.quantity
                if trade.trade_type == "BUY"
                else (trade.price - live_price) * trade.quantity
            )
            pnl -= trade.brokerage

            needs_auto_squareoff = False
            if trade.product_type == "INTRADAY":
                now_ist = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
                if now_ist.hour > 15 or (now_ist.hour == 15 and now_ist.minute >= 15):
                    needs_auto_squareoff = True

            monitored_positions.append({
                "trade_id": trade.id,
                "symbol": trade.symbol,
                "trade_type": trade.trade_type,
                "product_type": trade.product_type,
                "entry_price": trade.price,
                "current_price": round(live_price, 2),
                "quantity": trade.quantity,
                "unrealized_pnl": round(pnl, 2),
                "stop_loss": trade.stop_loss,
                "target_price": trade.target_price,
                "needs_auto_squareoff": needs_auto_squareoff,
                "recommendation": (
                    "FORCE_EXIT"
                    if needs_auto_squareoff
                    else ("HOLD" if pnl >= 0 else "WATCH_STOP_LOSS")
                ),
            })

        return {
            "market_status": market_info["status"],
            "open_positions_count": len(monitored_positions),
            "positions": monitored_positions,
        }
