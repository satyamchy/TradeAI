import asyncio
import pytest
from app.services.performance_tracker import save_snapshot_from_data, evaluate_performance_history


def test_performance_tracking():
    mock_data = {
        "ticker": "TCS.NS",
        "symbol": "TCS",
        "name": "Tata Consultancy Services",
        "current_price": 4000.0,
        "currency": "INR",
        "overall_sentiment": "Positive",
        "intraday_assessment": {"bias": "Bullish"},
        "indicators": {"period_return_pct": 5.2},
    }

    # Save snapshot
    snap = asyncio.run(save_snapshot_from_data(mock_data))
    assert snap is not None
    assert snap.ticker == "TCS.NS"
    assert snap.initial_price == 4000.0

    # Evaluate history
    perf = asyncio.run(evaluate_performance_history("TCS.NS"))
    assert perf is not None
    assert perf["has_history"] is True
    assert perf["total_snapshots"] >= 1
    assert "overall_ai_accuracy_score_pct" in perf
