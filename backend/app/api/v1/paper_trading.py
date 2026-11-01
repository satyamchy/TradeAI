"""Owner-scoped paper trading workflow endpoints."""

from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.auth import current_user, require_trader
from app.modules.decision_engine.service import DecisionEngineError
from app.modules.execution.service import ExecutionError
from app.shared.contracts import DecisionResult, ExecutionResult
from app.workflows.paper_trading import (
    IdempotencyKeyConflict,
    PaperPositionView,
    PaperReassessmentView,
    PaperTradingServiceFactory,
    PaperTradingService,
    PaperTradingUnavailable,
    PaperWorkflowStartRequest,
    PaperWorkflowView,
)

router = APIRouter(prefix="/paper", tags=["paper trading"])


def _service(request: Request, user: dict) -> PaperTradingService:
    factory: PaperTradingServiceFactory | None = getattr(
        request.app.state, "paper_trading_service_factory", None
    )
    if factory is None:
        raise HTTPException(status_code=503, detail="Paper trading workflow is not available")
    try:
        return factory.for_user(user)
    except PaperTradingUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/workflows", response_model=PaperWorkflowView, status_code=status.HTTP_202_ACCEPTED)
async def start_workflow(
    body: PaperWorkflowStartRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=110),
) -> PaperWorkflowView:
    user = require_trader(request)
    try:
        return await _service(request, user).start(body.symbol, idempotency_key=idempotency_key)
    except IdempotencyKeyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/workflows/{analysis_id}", response_model=PaperWorkflowView)
async def get_workflow(analysis_id: UUID, request: Request) -> PaperWorkflowView:
    user = current_user(request)
    try:
        return await _service(request, user).get_workflow(analysis_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Paper workflow not found") from exc


@router.post("/workflows/{analysis_id}/advance", response_model=PaperWorkflowView)
async def advance_workflow(analysis_id: UUID, request: Request) -> PaperWorkflowView:
    user = require_trader(request)
    try:
        return await _service(request, user).advance(analysis_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Paper workflow not found") from exc
    except DecisionEngineError as exc:
        raise HTTPException(status_code=409, detail="Decision inputs are not ready") from exc
    except ExecutionError as exc:
        raise HTTPException(status_code=409, detail="Paper execution could not be completed") from exc


@router.get("/decisions", response_model=list[DecisionResult])
async def list_decisions(request: Request, analysis_id: UUID | None = None) -> list[DecisionResult]:
    user = current_user(request)
    return await _service(request, user).list_decisions(analysis_id=analysis_id)


@router.get("/orders", response_model=list[ExecutionResult])
async def list_orders(request: Request) -> list[ExecutionResult]:
    user = current_user(request)
    return await _service(request, user).list_orders()


@router.post("/orders/{order_id}/reconcile", response_model=ExecutionResult)
async def reconcile_order(order_id: UUID, request: Request) -> ExecutionResult:
    user = require_trader(request)
    try:
        return await _service(request, user).reconcile_order(order_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Paper order not found") from exc


@router.get("/positions", response_model=list[PaperPositionView])
async def list_positions(request: Request) -> list[PaperPositionView]:
    user = current_user(request)
    return await _service(request, user).list_positions()


@router.post("/positions/{symbol}/reassess", response_model=PaperReassessmentView)
async def reassess_position(symbol: str, request: Request) -> PaperReassessmentView:
    user = require_trader(request)
    try:
        return await _service(request, user).reassess(symbol)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DecisionEngineError as exc:
        raise HTTPException(status_code=409, detail="Fresh risk or market inputs are unavailable") from exc
    except ExecutionError as exc:
        raise HTTPException(status_code=409, detail="Paper exit execution could not be completed") from exc
