"""Versioned API composition with the existing routes mounted as adapters."""

from fastapi import APIRouter

from app.api.account import router as account_router
from app.api.auth import router as auth_router
from app.api.automation import router as automation_router
from app.api.events import router as events_router
from app.api.manual_orders import router as manual_orders_router
from app.api.screener import router as screener_router
from app.api.suggestions import router as suggestions_router
from app.api.users import router as users_router
from app.api.v1.analysis_jobs import router as analysis_jobs_router

router = APIRouter()

for compatibility_router in (
    auth_router,
    users_router,
    automation_router,
    account_router,
    screener_router,
    manual_orders_router,
    suggestions_router,
    events_router,
):
    router.include_router(compatibility_router)

router.include_router(analysis_jobs_router)
