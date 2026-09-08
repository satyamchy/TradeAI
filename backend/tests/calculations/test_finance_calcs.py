import numpy as np
import pytest
from app.calculations.finance_calcs import (
    calculate_sma,
    calculate_rsi,
    calculate_volatility,
    calculate_period_return,
    calculate_drawdown,
    calculate_ema,
    calculate_macd,
    calculate_bollinger_bands,
    calculate_pivot_points,
    calculate_volume_trend,
)


def test_calculate_sma():
    prices = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
    assert calculate_sma(prices, 3) == 40.0
    assert calculate_sma(prices, 10) is None


def test_calculate_rsi():
    prices = np.array([10.0, 12.0, 11.0, 13.0, 15.0, 14.0, 16.0, 18.0, 17.0, 19.0, 21.0, 20.0, 22.0, 24.0, 23.0])
    rsi = calculate_rsi(prices, window=14)
    assert rsi is not None
    assert 0 <= rsi <= 100


def test_calculate_macd():
    # Provide enough data points (slow=26 + signal=9 = 35+)
    prices = np.linspace(10, 50, 40)
    macd_res = calculate_macd(prices)
    assert macd_res is not None
    assert "macd" in macd_res
    assert "signal" in macd_res
    assert "histogram" in macd_res
    assert macd_res["macd"] is not None


def test_calculate_bollinger_bands():
    prices = np.array([10, 12, 11, 13, 15, 14, 16, 18, 17, 19, 21, 20, 22, 24, 23, 25, 27, 26, 28, 30])
    bands = calculate_bollinger_bands(prices, window=20)
    assert bands is not None
    assert bands["upper"] > bands["middle"] > bands["lower"]


def test_calculate_pivot_points():
    pivots = calculate_pivot_points(high=100.0, low=90.0, close=95.0)
    assert pivots is not None
    assert pivots["pivot"] == 95.0
    assert pivots["r1"] == 100.0
    assert pivots["s1"] == 90.0
