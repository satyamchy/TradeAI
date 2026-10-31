"""Authenticated endpoints for durable Module 2 analysis jobs and results."""

from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.auth import current_user, require_trader
from app.jobs.schemas import AnalysisJobView
from app.jobs.service import AnalysisJobManager
from app.modules.ai_analysis.service import AIAnalysisService, InvalidAnalysisRequest
from app.modules.stock_selection.service import CandidateNotFoundError
from app.shared.contracts import AnalysisJobReceipt, AnalysisRequest, AnalysisResult
from app.workflows.analysis import CandidateNotReadyForAnalysis, StockSelectionAnalysisWorkflow

router = APIRouter(prefix="/analysis", tags=["analysis"])


def _manager(request: Request) -> AnalysisJobManager:
    manager = getattr(request.app.state, "analysis_job_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Analysis job service is not available")
    return manager


def _workflow(request: Request) -> StockSelectionAnalysisWorkflow:
    workflow = getattr(request.app.state, "stock_selection_analysis_workflow", None)
    if workflow is None:
        raise HTTPException(status_code=503, detail="Analysis workflow is not available")
    return workflow


def _analysis_service(request: Request) -> AIAnalysisService:
    service = getattr(request.app.state, "analysis_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Analysis service is not available")
    return service


@router.post("/jobs", response_model=AnalysisJobReceipt, status_code=status.HTTP_202_ACCEPTED)
async def submit_analysis_job(
    body: AnalysisRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
) -> AnalysisJobReceipt:
    """Validate Module 1 candidate data and enqueue an idempotent Module 2 run."""
    user = require_trader(request)
    try:
        return await _workflow(request).request_candidate_analysis(
            body.candidate_id,
            body,
            owner_id=int(user["id"]),
            idempotency_key=idempotency_key,
        )
    except CandidateNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Candidate not found") from exc
    except (CandidateNotReadyForAnalysis, InvalidAnalysisRequest, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/jobs/{analysis_id}", response_model=AnalysisJobView)
def get_analysis_job(analysis_id: UUID, request: Request) -> AnalysisJobView:
    """Return a job only to the user who submitted it."""
    user = current_user(request)
    job = _manager(request).get(analysis_id, owner_id=int(user["id"]))
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job not found")
    return job


@router.get("/results/{analysis_id}", response_model=AnalysisResult)
async def get_analysis_result(analysis_id: UUID, request: Request) -> AnalysisResult:
    user = current_user(request)
    result = await _analysis_service(request).get_analysis(analysis_id, owner_id=int(user["id"]))
    if result is not None:
        return result
    job = _manager(request).get(analysis_id, owner_id=int(user["id"]))
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis result not found")
    if job.status.value == "FAILED":
        raise HTTPException(status_code=422, detail=job.failure_message or "Analysis failed")
    raise HTTPException(status_code=409, detail="Analysis result is not ready")
