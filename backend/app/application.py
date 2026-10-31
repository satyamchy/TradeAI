"""Single FastAPI composition root for the TradeX modular monolith."""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app import db
from app.api.v1.router import router as api_v1_router
from app.auth import ensure_admin
from app.jobs.repository import SqlAlchemyAnalysisJobRepository
from app.jobs.service import AnalysisJobManager, AnalysisJobWorker
from app.modules.ai_analysis.profiles import default_profile_registry
from app.modules.ai_analysis.providers import AnalysisProvider, TradingAgentsProvider
from app.modules.ai_analysis.repository import SqlAlchemyAnalysisRunRepository
from app.modules.ai_analysis.service import AIAnalysisService
from app.modules.stock_selection.instrument_master import LocalNseInstrumentResolver
from app.modules.stock_selection.repository import SqlAlchemyCandidateRepository
from app.modules.stock_selection.service import StockSelectionService
from app.shared.config import settings
from app.shared.database import create_engine_for_database, create_session_factory
from app.shared.logging import bind_log_context, configure_logging, reset_log_context
from app.workflows.analysis import StockSelectionAnalysisWorkflow


def create_app(
    *,
    analysis_provider: AnalysisProvider | None = None,
) -> FastAPI:
    """Create the app and compose lazy services during its single lifespan."""
    app_settings = settings
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app_settings.validate_runtime()
        db.init_db()
        engine = create_engine_for_database(app_settings.database_path)
        sessions = create_session_factory(engine)
        manager = AnalysisJobManager(SqlAlchemyAnalysisJobRepository(sessions))
        instrument_master_path = Path(app_settings.instrument_master_path).expanduser()
        if not instrument_master_path.is_absolute():
            instrument_master_path = Path(__file__).resolve().parents[1] / instrument_master_path
        stock_selection_service = StockSelectionService(
            SqlAlchemyCandidateRepository(sessions),
            LocalNseInstrumentResolver(instrument_master_path),
        )
        provider = analysis_provider or TradingAgentsProvider(
            data_root=app_settings.tradingagents_data_dir,
            environment=f"{app_settings.app_env}-{app_settings.trading_mode}",
        )
        analysis_service = AIAnalysisService(
            jobs=manager,
            repository=SqlAlchemyAnalysisRunRepository(sessions),
            candidates=stock_selection_service,
            profiles=default_profile_registry(app_settings),
            provider=provider,
        )
        stock_selection_analysis_workflow = StockSelectionAnalysisWorkflow(
            stock_selection_service,
            analysis_service,
        )
        worker = AnalysisJobWorker(manager, analysis_service.handle_job)
        app.state.db_engine = engine
        app.state.db_session_factory = sessions
        app.state.analysis_job_manager = manager
        app.state.stock_selection_service = stock_selection_service
        app.state.analysis_service = analysis_service
        app.state.stock_selection_analysis_workflow = stock_selection_analysis_workflow
        app.state.analysis_job_worker = worker
        ensure_admin()

        runner = None
        try:
            await worker.start()
            from app.harness import get_automation_runner

            runner = get_automation_runner()
            await runner.start()
            yield
        finally:
            if runner is not None:
                await runner.stop()
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
