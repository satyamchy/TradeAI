"""
Technical Analysis Service.
Calculates indicators strictly deterministically:
SMA, EMA, RSI, MACD, Bollinger Bands, ATR, RVOL, Momentum, Support/Resistance, Price Change %, and Intraday Range.
Differentiates between Intraday and Delivery analysis.
"""

from typing import Any, Dict, List, Optional
import numpy as np


def _clean(val: Any, decimals: int = 2) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return None
        return round(f, decimals)
    except (TypeError, ValueError):
        return None


def calculate_sma(series: np.ndarray, window: int) -> Optional[float]:
    if len(series) < window:
        return None
    return _clean(np.mean(series[-window:]))


def calculate_ema(series: np.ndarray, window: int) -> Optional[float]:
    if len(series) < window:
        return None
    alpha = 2.0 / (window + 1)
    ema = float(series[0])
    for p in series[1:]:
        ema = (float(p) * alpha) + (ema * (1.0 - alpha))
    return _clean(ema)


def calculate_rsi(series: np.ndarray, window: int = 14) -> Optional[float]:
    if len(series) < window + 1:
        return None
    deltas = np.diff(series)
    gains = np.clip(deltas, 0, None)
    losses = -np.clip(deltas, None, 0)
    avg_gain = np.mean(gains[-window:])
    avg_loss = np.mean(losses[-window:])
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return _clean(100.0 - (100.0 / (1.0 + rs)))


def calculate_macd(
    series: np.ndarray, fast: int = 12, slow: int = 26, signal_window: int = 9
) -> Dict[str, Optional[Any]]:
    if len(series) < slow + signal_window:
        return {"macd": None, "signal": None, "histogram": None, "trend": "NEUTRAL"}

    alpha_fast = 2.0 / (fast + 1)
    alpha_slow = 2.0 / (slow + 1)

    fast_series = []
    slow_series = []
    ef = float(series[0])
    es = float(series[0])

    for p in series:
        ef = (float(p) * alpha_fast) + (ef * (1.0 - alpha_fast))
        es = (float(p) * alpha_slow) + (es * (1.0 - alpha_slow))
        fast_series.append(ef)
        slow_series.append(es)

    macd_line = np.array(fast_series) - np.array(slow_series)
    if len(macd_line) < signal_window:
        return {"macd": None, "signal": None, "histogram": None, "trend": "NEUTRAL"}

    alpha_sig = 2.0 / (signal_window + 1)
    sig = float(macd_line[0])
    for m in macd_line:
        sig = (float(m) * alpha_sig) + (sig * (1.0 - alpha_sig))

    macd_val = _clean(macd_line[-1])
    sig_val = _clean(sig)
    hist_val = _clean(macd_line[-1] - sig) if macd_val is not None and sig_val is not None else None

    trend = "BULLISH" if (hist_val and hist_val > 0) else ("BEARISH" if (hist_val and hist_val < 0) else "NEUTRAL")
    return {
        "macd": macd_val,
        "signal": sig_val,
        "histogram": hist_val,
        "trend": trend,
    }


def calculate_bollinger_bands(
    series: np.ndarray, window: int = 20, num_std: float = 2.0
) -> Dict[str, Optional[float]]:
    if len(series) < window:
        return {"upper": None, "middle": None, "lower": None, "bandwidth": None}
    recent = series[-window:]
    middle = float(np.mean(recent))
    std = float(np.std(recent))
    upper = middle + (num_std * std)
    lower = middle - (num_std * std)
    bandwidth = ((upper - lower) / middle * 100.0) if middle > 0 else 0.0
    return {
        "upper": _clean(upper),
        "middle": _clean(middle),
        "lower": _clean(lower),
        "bandwidth": _clean(bandwidth),
    }


def calculate_atr(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, window: int = 14
) -> Optional[float]:
    """Average True Range for volatility & dynamic stop-loss/target calculations."""
    if len(closes) < 2 or len(highs) != len(closes) or len(lows) != len(closes):
        return None
    tr_list = []
    for i in range(1, len(closes)):
        h = float(highs[i])
        l = float(lows[i])
        prev_c = float(closes[i - 1])
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        tr_list.append(tr)
    if len(tr_list) < window:
        return _clean(np.mean(tr_list)) if tr_list else None
    return _clean(np.mean(tr_list[-window:]))


def calculate_relative_volume(volumes: np.ndarray, window: int = 20) -> Dict[str, Optional[float]]:
    """Current volume compared to moving average volume."""
    if len(volumes) < 2:
        return {"current_volume": None, "avg_volume": None, "rvol": None}
    current_vol = float(volumes[-1])
    lookback = volumes[:-1]
    if len(lookback) < 1:
        return {"current_volume": _clean(current_vol, 0), "avg_volume": None, "rvol": 1.0}
    avg_vol = float(np.mean(lookback[-window:])) if len(lookback) >= window else float(np.mean(lookback))
    rvol = (current_vol / avg_vol) if avg_vol > 0 else 1.0
    return {
        "current_volume": _clean(current_vol, 0),
        "avg_volume": _clean(avg_vol, 0),
        "rvol": _clean(rvol, 2),
    }


def calculate_momentum(series: np.ndarray, window: int = 10) -> Optional[float]:
    """Rate of Change (ROC %) over specified lookback window."""
    if len(series) < window + 1:
        if len(series) >= 2 and series[0] > 0:
            return _clean(((series[-1] - series[0]) / series[0]) * 100.0)
        return None
    base_val = float(series[-window - 1])
    if base_val == 0:
        return None
    return _clean(((float(series[-1]) - base_val) / base_val) * 100.0)


def calculate_support_resistance(
    high: float, low: float, close: float, series_highs: Optional[np.ndarray] = None, series_lows: Optional[np.ndarray] = None
) -> Dict[str, Optional[float]]:
    """Calculates standard Floor Pivot Points + 20-period swing high/low."""
    if high is None or low is None or close is None:
        return {"pivot": None, "r1": None, "r2": None, "s1": None, "s2": None, "swing_high": None, "swing_low": None}
    p = (high + low + close) / 3.0
    r1 = (2.0 * p) - low
    s1 = (2.0 * p) - high
    r2 = p + (high - low)
    s2 = p - (high - low)

    swing_high = float(np.max(series_highs[-20:])) if (series_highs is not None and len(series_highs) > 0) else high
    swing_low = float(np.min(series_lows[-20:])) if (series_lows is not None and len(series_lows) > 0) else low

    return {
        "pivot": _clean(p),
        "r1": _clean(r1),
        "r2": _clean(r2),
        "s1": _clean(s1),
        "s2": _clean(s2),
        "swing_high": _clean(swing_high),
        "swing_low": _clean(swing_low),
    }


def run_technical_analysis(
    market_data: Dict[str, Any], analysis_type: str = "intraday"
) -> Dict[str, Any]:
    """
    Computes full technical indicators suite based on provided market data.
    Takes market_data dictionary prepared by market_data_service.
    """
    hist = market_data.get("history", [])
    intraday_candles = market_data.get("intraday_candles", [])
    quote = market_data.get("quote", {})

    is_intraday = analysis_type.lower() == "intraday"
    candles = intraday_candles if (is_intraday and len(intraday_candles) >= 5) else hist

    if not candles:
        closes = np.array([quote.get("current_price", 100.0)])
        highs = np.array([quote.get("day_high", 100.0)])
        lows = np.array([quote.get("day_low", 100.0)])
        volumes = np.array([quote.get("volume", 1000.0)])
    else:
        closes = np.array([c.get("close", 0.0) for c in candles], dtype=float)
        highs = np.array([c.get("high", c.get("close", 0.0)) for c in candles], dtype=float)
        lows = np.array([c.get("low", c.get("close", 0.0)) for c in candles], dtype=float)
        volumes = np.array([c.get("volume", 0.0) for c in candles], dtype=float)

    curr_price = quote.get("current_price") or (closes[-1] if len(closes) > 0 else 0.0)
    prev_close = quote.get("previous_close") or (closes[-2] if len(closes) > 1 else curr_price)
    day_high = quote.get("day_high") or (max(highs) if len(highs) > 0 else curr_price)
    day_low = quote.get("day_low") or (min(lows) if len(lows) > 0 else curr_price)

    price_change_pct = _clean(((curr_price - prev_close) / prev_close * 100.0) if prev_close > 0 else 0.0)
    intraday_range = _clean(day_high - day_low)
    intraday_range_pct = _clean((intraday_range / prev_close * 100.0) if prev_close > 0 else 0.0)

    # Indicator Calculations
    sma_20 = calculate_sma(closes, 20)
    sma_50 = calculate_sma(closes, 50)
    sma_200 = calculate_sma(closes, 200)

    ema_9 = calculate_ema(closes, 9)
    ema_21 = calculate_ema(closes, 21)

    rsi_14 = calculate_rsi(closes, 14) or 50.0
    macd_res = calculate_macd(closes)
    bb_res = calculate_bollinger_bands(closes, 20)
    atr = calculate_atr(highs, lows, closes, 14) or _clean(curr_price * 0.015)
    rvol_res = calculate_relative_volume(volumes, 20)
    momentum = calculate_momentum(closes, 10)
    sr_res = calculate_support_resistance(day_high, day_low, curr_price, highs, lows)

    # Intraday specific VWAP
    vwap = None
    if is_intraday and len(candles) > 0:
        vol_sum = np.sum(volumes)
        if vol_sum > 0:
            vwap = _clean(np.sum(((highs + lows + closes) / 3.0) * volumes) / vol_sum)
        else:
            vwap = _clean((day_high + day_low + curr_price) / 3.0)

    # Technical Trend Interpretation
    trend = "NEUTRAL"
    if sma_20 and curr_price > sma_20:
        if ema_9 and ema_21 and ema_9 > ema_21:
            trend = "STRONG_BULLISH" if rsi_14 > 55 else "BULLISH"
    elif sma_20 and curr_price < sma_20:
        if ema_9 and ema_21 and ema_9 < ema_21:
            trend = "STRONG_BEARISH" if rsi_14 < 45 else "BEARISH"

    return {
        "analysis_type": analysis_type.lower(),
        "price_change_pct": price_change_pct,
        "intraday_range": intraday_range,
        "intraday_range_pct": intraday_range_pct,
        "trend": trend,
        "moving_averages": {
            "sma_20": sma_20,
            "sma_50": sma_50,
            "sma_200": sma_200,
            "ema_9": ema_9,
            "ema_21": ema_21,
        },
        "rsi_14": rsi_14,
        "macd": macd_res,
        "bollinger_bands": bb_res,
        "atr": atr,
        "volume_analysis": rvol_res,
        "momentum_pct": momentum,
        "support_resistance": sr_res,
        "vwap": vwap,
    }
