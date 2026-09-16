"""TradeAI API entrypoint.

Only the intentionally small public API surface is registered here.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import ai_routes, market_routes, trading_routes
from app.config import settings
# from app.db.base import init_db

app = FastAPI(
    title="TradeX API",
    version="3.0.0",
    debug=settings.app_debug,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# @app.on_event("startup")
# async def startup() -> None:
#     await init_db()


# app.include_router(trading_routes.router, prefix=settings.api_version_prefix)
# app.include_router(ai_routes.router, prefix=settings.api_version_prefix)
app.include_router(market_routes.router, prefix=settings.api_version_prefix)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=settings.app_debug,
    )
