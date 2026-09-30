"""TradeX API entrypoint.

The mounted routes are the intraday automation loop, account reads,
the NIFTY 50 screener, and one-off intraday orders.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.account import router as account_router
from app.api.automation import router as automation_router
from app.api.manual_orders import router as manual_orders_router
from app.api.screener import router as screener_router
from app.config import settings
from app.trading.automation_runner import automation_runner


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Entries stay off until the enable route is called. A restart does not resume them.
    await automation_runner.start()
    yield
    await automation_runner.stop()


app = FastAPI(
    title="TradeX API",
    version="3.0.0",
    debug=settings.app_debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(automation_router, prefix=settings.api_version_prefix)
app.include_router(account_router, prefix=settings.api_version_prefix)
app.include_router(screener_router, prefix=settings.api_version_prefix)
app.include_router(manual_orders_router, prefix=settings.api_version_prefix)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=settings.app_debug,
    )
