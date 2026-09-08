from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.api import (
    analysis_routes,
    trade_routes,
    job_routes,
    market_routes,
    data_routes,
    trading_routes,
    stock_analysis_routes,
    conversation,
)
from app.config import settings
from app.database import init_db as init_legacy_db
from app.db.base import init_db as init_app_db

app = FastAPI(
    title="StockAI - Indian Stock Market Analyzer",
    debug=settings.app_debug,
    description=(
        "AI-powered Indian Stock Market Analyzer & Trading Platform. "
        "Covers NSE/BSE equities, Gold, Silver with DhanHQ broker integration, "
        "AI agent-driven analysis, intraday auto-squareoff, and trading guardrails."
    ),
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    await init_legacy_db()
    await init_app_db()


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "app": "OneAI Indian Stock Market Analyzer v2.0"}


# API Routers
app.include_router(stock_analysis_routes.router, prefix="/api/v1")
app.include_router(data_routes.router, prefix=settings.api_version_prefix)
app.include_router(analysis_routes.router, prefix=settings.api_version_prefix)
app.include_router(market_routes.router, prefix=settings.api_version_prefix)
app.include_router(trading_routes.router, prefix=settings.api_version_prefix)
app.include_router(trade_routes.router, prefix=settings.api_version_prefix)
app.include_router(job_routes.router, prefix=settings.api_version_prefix)

# Conversation Router
app.include_router(conversation.router, prefix="/api/conversation")
app.include_router(conversation.router, prefix="/v1/conversation")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
