"""Rank NIFTY 50 names for an intraday long or an intraday short.

The screener does not place orders. Live candles come from the DhanHQ
gateway. In paper mode, yfinance is the fallback when Dhan has no bars.
"""

from __future__ import annotations

import pandas as pd
import numpy as np

from app.broker import dhan_gateway
from app.config import settings
from app.market import nse_public
from app.trading.nifty50 import canonical_index, normalize_symbol
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


async def rank_nifty50(
    side: str,
    exclude: set[str] | None = None,
    limit: int | None = None,
    index: str | None = None,
) -> list[dict]:
    """Rank one NSE index.

    The order of names comes from the NSE snapshot. Dhan session candles
    refine the shortlist when today's bars are long enough. `exclude` is
    symbols already held. `limit` defaults to the configured screener size.
    """
    skipped = {normalize_symbol(symbol) for symbol in (exclude or set())}
    keep = limit or settings.screener_limit
    index_name = canonical_index(index)
    try:
        snapshot = await nse_public.snapshot(index_name)
    except Exception as exc:
        logger.warning("index snapshot failed: %s", exc)
        snapshot = []
    rows = []
    for item in snapshot:
        symbol = normalize_symbol(item["symbol"])
        if symbol in skipped:
            continue
        rows.append(
            {
                "symbol": symbol,
                "ltp": float(item.get("ltp") or 0),
                "percent_change": float(item.get("percent_change") or 0),
                "score": float(item.get("percent_change") or 0),
            }
        )
    shortlist = order_candidates(rows, side, max(keep * 3, keep))
    scored: list[dict] = []
    for item in shortlist:
        try:
            candle_score = score_candles(item["symbol"], await fetch_candles(item["symbol"]))
        except Exception as exc:
            logger.warning("screener skipped %s: %s", item["symbol"], exc)
            candle_score = None
        if candle_score:
            candle_score["ltp"] = item["ltp"] or candle_score["ltp"]
            scored.append(candle_score)
        else:
            scored.append(item)
    return order_candidates(scored, side, keep)


async def allowed_symbols(index: str | None = None) -> set[str]:
    """Constituents of the selected index. Empty when that index cannot be loaded."""
    symbols = await nse_public.constituents(canonical_index(index))
    return {normalize_symbol(symbol) for symbol in symbols}


async def last_traded_prices(symbols: list[str]) -> dict[str, float]:
    """Dhan quote for each symbol, in INR. Names with no quote are omitted.

    This is the process-token path. A trader gateway prefers its own token.
    """
    if not symbols or not dhan_gateway.is_dhan_configured():
        return {}
    mapping: dict[str, str] = {}
    for symbol in symbols:
        normalized = normalize_symbol(symbol)
        try:
            security_id = await dhan_gateway.resolve_security_id(normalized)
        except Exception as exc:
            logger.warning("price lookup skipped %s: %s", normalized, exc)
            continue
        if security_id:
            mapping[normalized] = security_id
    try:
        return await dhan_gateway.quote_prices(mapping)
    except Exception as exc:
        logger.warning("Dhan quote failed: %s", exc)
        return {}


async def fetch_candles(symbol: str) -> pd.DataFrame | None:
    """Today's 15-minute bars from Dhan, in IST. No other source."""
    normalized = normalize_symbol(symbol)
    if not dhan_gateway.is_dhan_configured():
        return None
    security_id = await dhan_gateway.resolve_security_id(normalized)
    if not security_id:
        logger.info("no Dhan security id for %s", normalized)
        return None
    return await dhan_gateway.fetch_intraday_candles(normalized, security_id)


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
