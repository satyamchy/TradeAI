"""Single FastAPI composition root for the TradeX modular monolith."""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app import db
from app.api.v1.router import router as api_v1_router
from app.auth import ensure_admin
from app.jobs.models import AnalysisJobRecord  # noqa: F401 - register model metadata
from app.jobs.repository import SqlAlchemyAnalysisJobRepository
from app.jobs.service import AnalysisHandler, AnalysisJobManager, AnalysisJobWorker
from app.shared.config import settings
from app.shared.database import create_engine_for_database, create_session_factory
from app.shared.logging import bind_log_context, configure_logging, reset_log_context


def create_app(
    *,
    analysis_handler: AnalysisHandler | None = None,
) -> FastAPI:
    """Create the one application and inject shared infrastructure at startup."""
    app_settings = settings
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app_settings.validate_runtime()
        db.init_db()
        engine = create_engine_for_database(app_settings.database_path)
        sessions = create_session_factory(engine)
        manager = AnalysisJobManager(SqlAlchemyAnalysisJobRepository(sessions))
        worker = AnalysisJobWorker(manager, analysis_handler) if analysis_handler else None
        app.state.db_engine = engine
        app.state.db_session_factory = sessions
        app.state.analysis_job_manager = manager
        app.state.analysis_job_worker = worker
        ensure_admin()

        runner = None
        try:
            if worker is not None:
                await worker.start()
            from app.harness import get_automation_runner

            runner = get_automation_runner()
            await runner.start()
            yield
        finally:
            if runner is not None:
                await runner.stop()
            if worker is not None:
                await worker.stop()
            engine.dispose()

    app = FastAPI(
        title="TradeX API",
        version="3.1.0",
        debug=app_settings.app_debug,
        lifespan=lifespan,
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=app_settings.session_secret,
        session_cookie="tradex_session",
        same_site="lax",
        https_only=app_settings.app_env.strip().lower() == "production",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[app_settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next: Any):
        supplied = request.headers.get("X-Request-ID", "")
        request_id = supplied if re.fullmatch(r"[A-Za-z0-9._-]{1,128}", supplied) else str(uuid4())
        tokens = bind_log_context(request_id=request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            reset_log_context(tokens)

    app.include_router(api_v1_router, prefix=app_settings.api_version_prefix)
    return app


app = create_app()
