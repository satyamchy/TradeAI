import asyncio
import pytest
from app.tools.finance.market_overview_tool import get_market_overview
from app.tools.finance.stock_screener_tool import screen_stocks


def test_get_market_overview():
    res = asyncio.run(get_market_overview())
    assert res is not None
    assert "market_status" in res
    assert res["market_status"] in ["Bullish", "Bearish", "Neutral"]
    assert "indices" in res
    assert len(res["indices"]) > 0


def test_screen_stocks():
    res = asyncio.run(screen_stocks(criteria="momentum", top_n=3))
    assert res is not None
    assert "screening_criteria" in res
    assert res["screening_criteria"] == "momentum"
    assert "ranked_stocks" in res
    assert len(res["ranked_stocks"]) <= 3
