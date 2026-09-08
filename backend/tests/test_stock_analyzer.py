"""
Phase 1 Stock Market Analyzer Backend Tests.
Tests:
1. GET /health returns status ok.
2. Technical analysis functions (SMA, EMA, RSI, MACD, Bollinger Bands, ATR, RVOL, Momentum, Support/Resistance).
3. POST /api/v1/stocks/analyze with mode: "selected", symbol: "TCS.NS", analysis_type: "intraday".
4. POST /api/v1/stocks/analyze with company name "Analyze Reliance" resolves to "RELIANCE.NS".
5. POST /api/v1/stocks/analyze with multiple symbols ["TCS.NS", "INFY.NS"] for "delivery" with fundamentals.
6. POST /api/v1/stocks/analyze with mode: "top_movers".
7. Verifies database logging of each analyzed stock into stock_analysis_snapshots.
"""

import pytest
import numpy as np
from httpx import AsyncClient, ASGITransport
from main import app
from app.services.company_resolver import resolve_ticker_symbol
from app.services.technical_analysis_service import (
    calculate_sma,
    calculate_ema,
    calculate_rsi,
    calculate_macd,
    calculate_bollinger_bands,
    calculate_atr,
    calculate_relative_volume,
    calculate_momentum,
    calculate_support_resistance,
    run_technical_analysis,
)
from app.database import AsyncSessionLocal
from app.models.stock_models import StockAnalysisSnapshot
from sqlalchemy.future import select


import asyncio

def test_health_check():
    async def _run():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/health")
            assert res.status_code == 200
            data = res.json()
            assert data.get("status") == "ok"
    asyncio.run(_run())


def test_company_resolver():
    assert resolve_ticker_symbol("Analyze TCS") == "TCS.NS"
    assert resolve_ticker_symbol("TCS.NS") == "TCS.NS"
    assert resolve_ticker_symbol("Reliance") == "RELIANCE.NS"
    assert resolve_ticker_symbol("State Bank of India") == "SBIN.NS"
    assert resolve_ticker_symbol("INFY") == "INFY.NS"


def test_technical_calculations():
    closes = np.array([100.0 + i for i in range(30)], dtype=float)
    highs = closes + 2.0
    lows = closes - 2.0
    volumes = np.array([10000 + i * 500 for i in range(30)], dtype=float)

    # Test SMA & EMA
    sma = calculate_sma(closes, 20)
    assert sma is not None
    assert sma > 0

    ema = calculate_ema(closes, 9)
    assert ema is not None
    assert ema > 0

    # Test RSI
    rsi = calculate_rsi(closes, 14)
    assert rsi is not None
    assert 0 <= rsi <= 100

    # Test MACD
    macd = calculate_macd(closes)
    assert macd is not None
    assert "macd" in macd
    assert "signal" in macd
    assert "trend" in macd

    # Test Bollinger Bands
    bb = calculate_bollinger_bands(closes, 20)
    assert bb["upper"] > bb["middle"] > bb["lower"]

    # Test ATR
    atr = calculate_atr(highs, lows, closes, 14)
    assert atr is not None
    assert atr > 0

    # Test Relative Volume
    rvol = calculate_relative_volume(volumes, 20)
    assert rvol["rvol"] is not None

    # Test Momentum
    mom = calculate_momentum(closes, 10)
    assert mom is not None

    # Test Support & Resistance
    sr = calculate_support_resistance(130.0, 110.0, 125.0)
    assert sr["pivot"] is not None
    assert sr["r1"] > sr["pivot"] > sr["s1"]


def test_analyze_single_selected_stock_intraday():
    async def _run():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "mode": "selected",
                "symbols": ["TCS.NS"],
                "analysis_type": "intraday",
                "date": "2026-09-04",
            }
            res = await client.post("/api/v1/stocks/analyze", json=payload)
            assert res.status_code == 200, f"Error: {res.text}"
            data = res.json()
            assert isinstance(data, list)
            assert len(data) >= 1

            first = data[0]
            assert first["symbol"] == "TCS.NS"
            assert first["analysis_type"] == "intraday"
            assert first["recommendation"] in ["BUY", "HOLD", "AVOID"]
            assert 0.0 <= first["confidence"] <= 1.0
            assert first["risk_level"] in ["LOW", "MEDIUM", "HIGH"]
            assert len(first["summary"]) > 0
            assert "selling_point" in first
            assert "market_data" in first
            assert "technical_analysis" in first
            assert "disclaimer" in first
    asyncio.run(_run())


def test_analyze_company_name_resolution():
    async def _run():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "mode": "selected",
                "symbols": ["Analyze Reliance"],
                "analysis_type": "intraday",
            }
            res = await client.post("/api/v1/stocks/analyze", json=payload)
            assert res.status_code == 200, f"Error: {res.text}"
            data = res.json()
            assert len(data) >= 1
            assert data[0]["symbol"] == "RELIANCE.NS"
    asyncio.run(_run())


def test_analyze_multiple_delivery_stocks():
    async def _run():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "mode": "selected",
                "symbols": ["TCS.NS", "INFY.NS"],
                "analysis_type": "delivery",
            }
            res = await client.post("/api/v1/stocks/analyze", json=payload)
            assert res.status_code == 200, f"Error: {res.text}"
            data = res.json()
            assert len(data) == 2
            symbols = [d["symbol"] for d in data]
            assert "TCS.NS" in symbols
            assert "INFY.NS" in symbols

            # Verify delivery includes fundamentals
            for item in data:
                assert item["analysis_type"] == "delivery"
                assert "fundamentals" in item["market_data"]
    asyncio.run(_run())


def test_analyze_top_movers():
    async def _run():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "mode": "top_movers",
                "analysis_type": "intraday",
                "top_n": 3,
            }
            res = await client.post("/api/v1/stocks/analyze", json=payload)
            assert res.status_code == 200, f"Error: {res.text}"
            data = res.json()
            assert len(data) <= 3
            assert len(data) > 0
    asyncio.run(_run())


def test_database_logging():
    async def _run():
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(StockAnalysisSnapshot).order_by(StockAnalysisSnapshot.id.desc()).limit(5)
            )
            rows = result.scalars().all()
            assert len(rows) > 0
            latest = rows[0]
            assert latest.ticker is not None
            assert latest.recommendation in ["BUY", "HOLD", "AVOID"]
            assert latest.structured_json is not None
    asyncio.run(_run())
