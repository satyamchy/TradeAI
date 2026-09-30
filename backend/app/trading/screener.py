"""Rank NIFTY 50 names for an intraday long or an intraday short.

The screener does not place orders. Live candles come from the DhanHQ
gateway. In paper mode, yfinance is the fallback when Dhan has no bars.
"""

from __future__ import annotations

import pandas as pd
import numpy as np

from app.broker import dhan_gateway
from app.config import settings
from app.trading.nifty50 import NIFTY50_SYMBOLS, normalize_symbol
from app.utils.logger import get_logger

logger = get_logger(__name__)


def score_candles(symbol: str, frame: pd.DataFrame | None) -> dict | None:
    """Score one symbol from OHLCV bars.

    Returns None when there are fewer than 20 bars, or when the range is
    too dead (ATR under 0.3 percent) or the RSI is outside 20–80.
    The score is a unitless rank, not a price and not a probability.
    """
    if frame is None or len(frame) < 20:
        return None

    close = frame["close"]
    first = float(close.iloc[0])
    last = float(close.iloc[-1])
    if not first or not last:
        return None

    percent_change = (last - first) / first * 100
    average_volume = float(frame["volume"].mean() or 0)
    volume_ratio = float(frame["volume"].iloc[-5:].mean() / average_volume) if average_volume else 0.0
    rsi = _rsi(close)
    atr_percent = _atr_percent(frame)
    vwap_deviation_percent = _vwap_deviation_percent(frame)

    if atr_percent < 0.3 or rsi > 80 or rsi < 20:
        return None

    score = (
        0.4 * percent_change
        + 0.3 * min(volume_ratio, 3.0)
        + 0.2 * vwap_deviation_percent
        + 0.1 * (50 - abs(rsi - 55))
    )
    return {
        "symbol": normalize_symbol(symbol),
        "ltp": last,
        "percent_change": round(percent_change, 2),
        "volume_ratio": round(volume_ratio, 2),
        "rsi": round(rsi, 1),
        "atr_percent": round(atr_percent, 2),
        "vwap_deviation_percent": round(vwap_deviation_percent, 2),
        "score": round(float(score), 3),
    }


def order_candidates(scored: list[dict], side: str, limit: int) -> list[dict]:
    """Highest scores for a long, lowest scores for a short.

    `side` is `long` or `short`. `limit` is the number of names to keep.
    """
    if side not in {"long", "short"}:
        raise ValueError("side must be long or short")
    ranked = sorted(scored, key=lambda row: row["score"], reverse=side == "long")
    return ranked[:limit]


async def rank_nifty50(side: str, exclude: set[str] | None = None, limit: int | None = None) -> list[dict]:
    """Rank the NIFTY 50 universe.

    `exclude` is symbols already held, so the cycle does not add to them.
    `limit` defaults to the configured screener size.
    """
    skipped = {normalize_symbol(symbol) for symbol in (exclude or set())}
    keep = limit or settings.screener_limit
    scored: list[dict] = []
    for symbol in NIFTY50_SYMBOLS:
        if symbol in skipped:
            continue
        try:
            row = score_candles(symbol, await fetch_candles(symbol))
        except Exception as exc:
            logger.warning("screener skipped %s: %s", symbol, exc)
            continue
        if row:
            scored.append(row)
    return order_candidates(scored, side, keep)


async def last_traded_prices(symbols: list[str]) -> dict[str, float]:
    """Latest close for each symbol, in INR. Symbols with no bars are omitted."""
    prices: dict[str, float] = {}
    for symbol in symbols:
        normalized = normalize_symbol(symbol)
        try:
            frame = await fetch_candles(normalized)
        except Exception as exc:
            logger.warning("price lookup skipped %s: %s", normalized, exc)
            continue
        if frame is not None and len(frame):
            prices[normalized] = float(frame["close"].iloc[-1])
    return prices


async def fetch_candles(symbol: str) -> pd.DataFrame | None:
    """15-minute bars. Dhan when it is configured, otherwise yfinance in paper mode only."""
    normalized = normalize_symbol(symbol)
    if dhan_gateway.is_dhan_configured():
        security_id = await dhan_gateway.resolve_security_id(normalized)
        if security_id:
            frame = await dhan_gateway.fetch_intraday_candles(normalized, security_id)
            if frame is not None:
                return frame
        if settings.trading_mode.strip().lower() != "paper":
            return None
    if settings.trading_mode.strip().lower() == "paper":
        return _yfinance_candles(normalized)
    return None


def _yfinance_candles(symbol: str) -> pd.DataFrame | None:
    import yfinance as yf

    frame = yf.Ticker(f"{symbol}.NS").history(period="5d", interval="15m")
    if frame is None or frame.empty:
        return None
    frame = frame.rename(columns=str.lower)
    return frame[["open", "high", "low", "close", "volume"]]


def _rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    latest = rsi.iloc[-1]
    if rsi.empty or np.isnan(latest):
        return 50.0
    return float(latest)


def _atr_percent(frame: pd.DataFrame, period: int = 14) -> float:
    high, low, close = frame["high"], frame["low"], frame["close"]
    previous_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - previous_close).abs(), (low - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(period).mean().iloc[-1]
    last = float(close.iloc[-1])
    if not last or np.isnan(atr):
        return 0.0
    return float(atr / last * 100)


def _vwap_deviation_percent(frame: pd.DataFrame) -> float:
    typical = (frame["high"] + frame["low"] + frame["close"]) / 3
    volume = frame["volume"].replace(0, np.nan)
    vwap = (typical * frame["volume"]).cumsum() / volume.cumsum()
    last_close = float(frame["close"].iloc[-1])
    last_vwap = float(vwap.iloc[-1]) if not np.isnan(vwap.iloc[-1]) else 0.0
    if not last_vwap:
        return 0.0
    return (last_close - last_vwap) / last_vwap * 100
