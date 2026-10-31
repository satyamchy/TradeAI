"""Authenticated manual-candidate endpoints for Stock Selection."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.auth import current_user, require_trader
from app.modules.stock_selection.schemas import CandidateFilters
from app.modules.stock_selection.service import (
    CandidateNotFoundError,
    StockSelectionService,
    StockSelectionUnavailableError,
    UnsupportedSelectionError,
)
from app.shared.contracts import Candidate, CandidateBatch, CreateCandidatesRequest

router = APIRouter(prefix="/stock-selection/candidates", tags=["stock selection"])


def _service(request: Request) -> StockSelectionService:
    service = getattr(request.app.state, "stock_selection_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Stock selection service is not available")
    return service


@router.post("", response_model=CandidateBatch, status_code=status.HTTP_201_CREATED)
async def create_candidates(body: CreateCandidatesRequest, request: Request) -> CandidateBatch:
    user = require_trader(request)
    try:
        return await _service(request).create_candidates(body, owner_id=int(user["id"]))
    except UnsupportedSelectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except StockSelectionUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("", response_model=list[Candidate])
async def list_candidates(
    request: Request,
    exchange: str | None = None,
    horizon: str | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[Candidate]:
    user = current_user(request)
    filters = CandidateFilters(
        exchange=exchange,
        horizon=horizon,
        created_after=created_after,
        created_before=created_before,
        limit=limit,
        offset=offset,
    )
    return await _service(request).list_candidates(filters, owner_id=int(user["id"]))


@router.get("/{candidate_id}", response_model=Candidate)
async def get_candidate(candidate_id: UUID, request: Request) -> Candidate:
    user = current_user(request)
    try:
        return await _service(request).get_candidate(candidate_id, owner_id=int(user["id"]))
    except CandidateNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Candidate not found") from exc
