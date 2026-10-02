"""TradeX API.

Routes: auth, users, automation, account, screener, orders, suggestions, events.
OpenAPI is served at /docs from the docstrings on those routes.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app import db
from app.api.account import router as account_router
from app.api.auth import router as auth_router
from app.api.automation import router as automation_router
from app.api.events import router as events_router
from app.api.manual_orders import router as manual_orders_router
from app.api.screener import router as screener_router
from app.api.suggestions import router as suggestions_router
from app.api.users import router as users_router
from app.auth import ensure_admin
from app.config import settings
from app.trading.automation_runner import automation_runner


def _refuse_unsafe_production() -> None:
    if settings.app_env.strip().lower() != "production":
        return
    if settings.session_secret == "dev-session-secret-change-me" or len(settings.session_secret) < 16:
        raise RuntimeError("Set a long SESSION_SECRET before APP_ENV=production")
    if not settings.credentials_key:
        raise RuntimeError("Set CREDENTIALS_KEY before APP_ENV=production")
    if settings.app_debug:
        raise RuntimeError("Set APP_DEBUG=false before APP_ENV=production")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _refuse_unsafe_production()
    db.init_db()
    ensure_admin()
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
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="tradex_session",
    same_site="lax",
    https_only=settings.app_env.strip().lower() == "production",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

prefix = settings.api_version_prefix
app.include_router(auth_router, prefix=prefix)
app.include_router(users_router, prefix=prefix)
app.include_router(automation_router, prefix=prefix)
app.include_router(account_router, prefix=prefix)
app.include_router(screener_router, prefix=prefix)
app.include_router(manual_orders_router, prefix=prefix)
app.include_router(suggestions_router, prefix=prefix)
app.include_router(events_router, prefix=prefix)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=settings.app_debug,
    )
