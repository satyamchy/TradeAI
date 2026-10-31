"""Module-oriented analysis job endpoints; analysis execution arrives with Module 2."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from app.auth import current_user
from app.jobs.schemas import AnalysisJobSubmission, AnalysisJobView
from app.jobs.service import AnalysisJobManager

router = APIRouter(prefix="/analysis/jobs", tags=["analysis jobs"])


def _manager(request: Request) -> AnalysisJobManager:
    manager = getattr(request.app.state, "analysis_job_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Analysis job service is not available")
    return manager


@router.post("", response_model=AnalysisJobView, status_code=status.HTTP_202_ACCEPTED)
def submit_analysis_job(body: AnalysisJobSubmission, request: Request) -> AnalysisJobView:
    """Persist an analysis request and return its stable `analysis_id`.

    The same user/key returns the existing job. The job remains pending until
    Module 2 registers an analysis handler during its implementation phase.
    """
    user = current_user(request)
    return _manager(request).submit(
        owner_id=int(user["id"]),
        idempotency_key=body.idempotency_key,
        request_payload=body.request_payload,
    )


@router.get("/{analysis_id}", response_model=AnalysisJobView)
def get_analysis_job(analysis_id: UUID, request: Request) -> AnalysisJobView:
    """Return a job only to the user who submitted it."""
    user = current_user(request)
    job = _manager(request).get(analysis_id, owner_id=int(user["id"]))
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job not found")
    return job
