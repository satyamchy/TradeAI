"""
Trading Harness Control & Debug API Router.

This is the fastest way to debug the harness without reading logs: one
endpoint shows whether the feed is connected, which strategies are
registered, how many ticks have run, and the last error seen anywhere in
the loop.

Endpoints:
- GET  /harness/status: Full harness state snapshot (see TradingHarness.status()).
- POST /harness/start: Starts the tick loop, feed, and watchdog scheduler.
- POST /harness/stop: Stops all three cleanly.
"""

from fastapi import APIRouter, HTTPException

from app.harness import harness

router = APIRouter(prefix="/harness", tags=["harness"])


@router.get("/status")
async def harness_status():
    """
    Full harness state — the first thing to check when a strategy isn't
    trading as expected.

    - **Purpose**: Debugging entry point for the whole backend harness.
    - **Method**: GET
    - **Response**:
      ```json
      {
        "running": true,
        "dhan_configured": true,
        "feed_connected": true,
        "feed_last_error": null,
        "market_open": true,
        "strategies": [{"name": "threshold_reliance", "symbol": "RELIANCE.NS", "security_id": "1333"}],
        "open_positions": ["RELIANCE.NS"],
        "tick_count": 214,
        "last_error": null
      }
      ```
    """
    return harness.status()


@router.post("/start")
async def harness_start():
    """
    Starts the harness: connects the live price feed for all registered
    strategies, starts the watchdog scheduler, and begins the tick loop.

    - **Purpose**: Turns the automated trading loop on.
    - **Method**: POST
    """
    try:
        await harness.start()
        return harness.status()
    except RuntimeError as err:
        raise HTTPException(status_code=400, detail=str(err))


@router.post("/stop")
async def harness_stop():
    """
    Stops the harness: closes the live feed, stops the watchdog scheduler,
    and exits the tick loop. Does not touch already-placed orders or open
    positions — use /trading/square-off/{trade_id} for that.

    - **Purpose**: Turns the automated trading loop off (separate from the
      Master Kill-Switch in /trading/guardrails, which blocks orders at the
      guardrail layer even if the harness keeps running).
    - **Method**: POST
    """
    await harness.stop()
    return harness.status()
