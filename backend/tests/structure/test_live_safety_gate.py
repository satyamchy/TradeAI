import asyncio

import pytest

from app.broker.dhan_gateway import LiveExecutionDisabled, _call
from app.config import settings


def test_live_mode_alone_cannot_mutate_broker_in_development(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "trading_mode", "live")
    monkeypatch.setattr(settings, "live_trading_enabled", False)

    with pytest.raises(LiveExecutionDisabled):
        asyncio.run(_call("place_order", creds=("test-client", "test-token")))

    assert settings.live_execution_allowed is False
