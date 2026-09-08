"""
Deterministic financial calculations. Pure functions, no LLM calls,
no network calls, no side effects. Every function here must be unit
tested (see tests/calculations/test_finance_calcs.py) and must return
None rather than a fabricated number when there isn't enough data.
"""

import numpy as np


def _clean(x) -> float | None:
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return None
    return round(float(x), 2)


def calculate_sma(closes: np.ndarray, window: int) -> float | None:
    if len(closes) < window:
        return None
    return _clean(np.mean(closes[-window:]))


def calculate_rsi(closes: np.ndarray, window: int = 14) -> float | None:
    if len(closes) < window + 1:
        return None
    deltas = np.diff(closes)
    gains = np.clip(deltas, 0, None)
    losses = -np.clip(deltas, None, 0)
    avg_gain = np.mean(gains[-window:])
    avg_loss = np.mean(losses[-window:])
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return _clean(100 - (100 / (1 + rs)))


def calculate_volatility(closes: np.ndarray) -> float | None:
    """Annualized volatility (%) from daily closes."""
    if len(closes) < 2:
        return None
    returns = np.diff(closes) / closes[:-1]
    return _clean(np.std(returns) * np.sqrt(252) * 100)


def calculate_period_return(closes: np.ndarray) -> float | None:
    if len(closes) < 2 or closes[0] == 0:
        return None
    return _clean((closes[-1] / closes[0] - 1) * 100)


def calculate_cagr(begin_value: float, end_value: float, years: float) -> float | None:
    if begin_value is None or end_value is None or years <= 0 or begin_value <= 0:
        return None
    return _clean(((end_value / begin_value) ** (1 / years) - 1) * 100)


def calculate_pe(price: float | None, eps: float | None) -> float | None:
    if price is None or eps is None or eps == 0:
        return None
    return _clean(price / eps)


def calculate_debt_to_equity(total_debt: float | None, shareholders_equity: float | None) -> float | None:
    if total_debt is None or shareholders_equity is None or shareholders_equity == 0:
        return None
    return _clean(total_debt / shareholders_equity)


def calculate_roe(net_income: float | None, shareholders_equity: float | None) -> float | None:
    if net_income is None or shareholders_equity is None or shareholders_equity == 0:
        return None
    return _clean((net_income / shareholders_equity) * 100)


def calculate_net_margin(net_income: float | None, revenue: float | None) -> float | None:
    if net_income is None or revenue is None or revenue == 0:
        return None
    return _clean((net_income / revenue) * 100)


def calculate_ema(closes: np.ndarray, window: int) -> float | None:
    if len(closes) < window:
        return None
    alpha = 2 / (window + 1)
    ema = float(closes[0])
    for price in closes[1:]:
        ema = (float(price) * alpha) + (ema * (1 - alpha))
    return _clean(ema)


def calculate_macd(
    closes: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9
) -> dict | None:
    """Calculates MACD Line, Signal Line, and MACD Histogram."""
    if len(closes) < slow + signal:
        return None
    
    alpha_fast = 2 / (fast + 1)
    alpha_slow = 2 / (slow + 1)
    
    ema_fast_series = []
    ema_slow_series = []
    
    ef = float(closes[0])
    es = float(closes[0])
    
    for price in closes:
        ef = (float(price) * alpha_fast) + (ef * (1 - alpha_fast))
        es = (float(price) * alpha_slow) + (es * (1 - alpha_slow))
        ema_fast_series.append(ef)
        ema_slow_series.append(es)
        
    macd_series = np.array(ema_fast_series) - np.array(ema_slow_series)
    
    if len(macd_series) < signal:
        return None
        
    alpha_signal = 2 / (signal + 1)
    sig = float(macd_series[0])
    for m in macd_series[1:]:
        sig = (float(m) * alpha_signal) + (sig * (1 - alpha_signal))
        
    macd_val = _clean(macd_series[-1])
    signal_val = _clean(sig)
    hist_val = _clean(macd_series[-1] - sig) if macd_val is not None and signal_val is not None else None
    
    return {
        "macd": macd_val,
        "signal": signal_val,
        "histogram": hist_val,
    }


def calculate_bollinger_bands(
    closes: np.ndarray, window: int = 20, num_std: float = 2.0
) -> dict | None:
    """Calculates Upper, Middle (SMA), and Lower Bollinger Bands."""
    if len(closes) < window:
        return None
    recent = closes[-window:]
    middle = np.mean(recent)
    std_dev = np.std(recent)
    upper = middle + (num_std * std_dev)
    lower = middle - (num_std * std_dev)
    return {
        "middle": _clean(middle),
        "upper": _clean(upper),
        "lower": _clean(lower),
    }


def calculate_pivot_points(high: float, low: float, close: float) -> dict | None:
    """Calculates standard floor pivot points (Pivot, S1, S2, R1, R2)."""
    if high is None or low is None or close is None:
        return None
    p = (high + low + close) / 3.0
    r1 = (2 * p) - low
    s1 = (2 * p) - high
    r2 = p + (high - low)
    s2 = p - (high - low)
    return {
        "pivot": _clean(p),
        "r1": _clean(r1),
        "r2": _clean(r2),
        "s1": _clean(s1),
        "s2": _clean(s2),
    }


def calculate_volume_trend(volumes: np.ndarray, window: int = 10) -> float | None:
    """Calculates recent volume ratio compared to moving average volume."""
    if len(volumes) < window + 1:
        return None
    recent_vol = volumes[-1]
    avg_vol = np.mean(volumes[-(window + 1):-1])
    if avg_vol == 0:
        return None
    return _clean(recent_vol / avg_vol)


def calculate_drawdown(closes: np.ndarray) -> float | None:
    """Maximum drawdown (%) over the given closes series."""
    if len(closes) < 2:
        return None
    running_max = np.maximum.accumulate(closes)
    drawdowns = (closes - running_max) / running_max
    return _clean(np.min(drawdowns) * 100)

