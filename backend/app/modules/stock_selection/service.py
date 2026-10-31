"""Typed Stock Selection application service."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

from app.modules.stock_selection.instrument_master import (
    AmbiguousInstrumentError,
    InstrumentMasterError,
    InstrumentResolver,
)
from app.modules.stock_selection.repository import CandidateRepository
from app.modules.stock_selection.schemas import (
    CandidateFilters,
    InstrumentResolution,
    RankCandidatesRequest,
    RankedCandidate,
)
from app.shared.contracts import (
    Candidate,
    CandidateBatch,
    CandidateBatchStatus,
    CandidateRejection,
    CandidateRejectionCode,
    CandidateValidationStatus,
    CreateCandidatesRequest,
    Instrument,
    SelectionMode,
)
from app.shared.logging import bind_log_context, get_logger, reset_log_context

logger = get_logger(__name__)


class StockSelectionError(RuntimeError):
    """Base error translated by the API boundary."""


class UnsupportedSelectionError(StockSelectionError):
    """The requested scanner or exchange is not available in this release."""


class CandidateNotFoundError(StockSelectionError):
    """No candidate exists in the requested user's visible scope."""


class StockSelectionUnavailableError(StockSelectionError):
    """A required local instrument source is unavailable or malformed."""


class RankingProvider(Protocol):
    async def rank(self, request: RankCandidatesRequest) -> list[RankedCandidate]:
        ...


class ExistingNiftyScreenerAdapter:
    """Temporary wrapper around the existing read-only screener implementation."""

    async def rank(self, request: RankCandidatesRequest) -> list[RankedCandidate]:
        # Lazy import keeps module imports inert and leaves the existing algorithm
        # in one place while its data/broker dependencies are migrated later.
        from app.trading.nifty50 import canonical_index
        from app.trading.screener import rank_nifty50

        rows = await rank_nifty50(
            request.side,
            limit=request.limit,
            index=canonical_index(request.index),
        )
        return [RankedCandidate.model_validate(row) for row in rows]


class StockSelectionService:
    """Validate manual symbols, persist an auditable batch, and expose the legacy scan."""

    def __init__(
        self,
        repository: CandidateRepository,
        instrument_resolver: InstrumentResolver,
        ranking_provider: RankingProvider | None = None,
    ):
        self._repository = repository
        self._instrument_resolver = instrument_resolver
        self._ranking_provider = ranking_provider or ExistingNiftyScreenerAdapter()

    async def create_candidates(
        self,
        request: CreateCandidatesRequest,
        *,
        owner_id: int | None = None,
    ) -> CandidateBatch:
        tokens = bind_log_context(module="stock_selection")
        try:
            return self._create_candidates(request, owner_id=owner_id)
        finally:
            reset_log_context(tokens)

    def _create_candidates(
        self,
        request: CreateCandidatesRequest,
        *,
        owner_id: int | None,
    ) -> CandidateBatch:
        if request.selection_mode is not SelectionMode.MANUAL:
            raise UnsupportedSelectionError("Only MANUAL stock selection is supported")
        exchange = request.exchange.strip().upper()
        if exchange != "NSE":
            raise UnsupportedSelectionError("Only NSE instruments are supported in this release")

        batch_id = uuid4()
        created_at = _utc_now()
        candidates: list[Candidate] = []
        rejections: list[CandidateRejection] = []
        seen: set[str] = set()

        for submitted_symbol in request.symbols:
            normalized, rejection = _normalize_symbol(submitted_symbol)
            if rejection is not None:
                rejections.append(rejection)
                continue
            assert normalized is not None
            if normalized in seen:
                rejections.append(
                    CandidateRejection(
                        submitted_symbol=submitted_symbol,
                        normalized_symbol=normalized,
                        code=CandidateRejectionCode.DUPLICATE_SYMBOL,
                        message=f"{normalized} appears more than once in this batch.",
                    )
                )
                continue
            seen.add(normalized)

            try:
                resolution = self._instrument_resolver.resolve(normalized, exchange)
            except AmbiguousInstrumentError:
                rejections.append(
                    CandidateRejection(
                        submitted_symbol=submitted_symbol,
                        normalized_symbol=normalized,
                        code=CandidateRejectionCode.AMBIGUOUS_SYMBOL,
                        message=f"{normalized} matches more than one NSE equity instrument.",
                    )
                )
                continue
            except InstrumentMasterError as exc:
                logger.error("Instrument master unavailable: %s", str(exc))
                raise StockSelectionUnavailableError("Instrument master is unavailable or malformed") from exc

            if resolution is None:
                rejections.append(
                    CandidateRejection(
                        submitted_symbol=submitted_symbol,
                        normalized_symbol=normalized,
                        code=CandidateRejectionCode.UNKNOWN_SYMBOL,
                        message=f"{normalized} is not present in the configured NSE instrument universe.",
                    )
                )
                continue
            _validate_resolution(resolution, normalized, exchange)
            candidates.append(
                Candidate(
                    candidate_id=uuid4(),
                    batch_id=batch_id,
                    instrument=resolution.instrument,
                    selection_mode=SelectionMode.MANUAL,
                    selection_reason="USER_SELECTED",
                    validation_status=(
                        CandidateValidationStatus.VALID
                        if resolution.instrument.security_id
                        else CandidateValidationStatus.ANALYSIS_ONLY
                    ),
                    mapping_source=resolution.mapping_source,
                    resolved_at=resolution.resolved_at,
                    created_at=created_at,
                )
            )

        if not rejections:
            batch_status = CandidateBatchStatus.COMPLETED
        elif candidates:
            batch_status = CandidateBatchStatus.PARTIAL
        else:
            batch_status = CandidateBatchStatus.REJECTED
        batch = CandidateBatch(
            batch_id=batch_id,
            status=batch_status,
            candidates=candidates,
            rejected_symbols=[item.submitted_symbol for item in rejections],
            rejections=rejections,
            created_at=created_at,
        )
        self._repository.create_batch(
            batch,
            request.symbols,
            owner_id,
            exchange=exchange,
            horizon=request.horizon.value,
        )
        return batch

    async def get_candidate(self, candidate_id: UUID, *, owner_id: int | None = None) -> Candidate:
        record = self._repository.get_candidate(candidate_id, owner_id)
        if record is None:
            raise CandidateNotFoundError("Candidate not found")
        return record

    async def list_candidates(
        self,
        filters: CandidateFilters,
        *,
        owner_id: int | None = None,
    ) -> list[Candidate]:
        return self._repository.list_candidates(filters, owner_id)

    async def rank_candidates(self, request: RankCandidatesRequest) -> list[RankedCandidate]:
        if self._ranking_provider is None:
            raise UnsupportedSelectionError("No ranking provider is registered")
        return await self._ranking_provider.rank(request)


_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9&-]{0,31}$")


def _normalize_symbol(value: str) -> tuple[str | None, CandidateRejection | None]:
    normalized = value.strip().upper()
    if not normalized:
        return None, CandidateRejection(
            submitted_symbol=value,
            code=CandidateRejectionCode.EMPTY_SYMBOL,
            message="A symbol is required.",
        )
    if normalized.endswith(".BO"):
        return None, CandidateRejection(
            submitted_symbol=value,
            code=CandidateRejectionCode.INVALID_SYMBOL,
            message="The .BO suffix is not valid for an NSE request.",
        )
    if normalized.endswith(".NS"):
        normalized = normalized[:-3]
    if not _SYMBOL_RE.fullmatch(normalized):
        return None, CandidateRejection(
            submitted_symbol=value,
            normalized_symbol=normalized or None,
            code=CandidateRejectionCode.INVALID_SYMBOL,
            message="Use a plain NSE trading symbol without embedded whitespace or unsupported punctuation.",
        )
    return normalized, None


def _validate_resolution(resolution: InstrumentResolution, symbol: str, exchange: str) -> None:
    instrument = resolution.instrument
    if instrument.symbol != symbol or instrument.exchange.upper() != exchange:
        raise StockSelectionUnavailableError("Instrument resolver returned a mismatched canonical mapping")
    if not instrument.analysis_ticker:
        raise StockSelectionUnavailableError("Instrument resolver returned no analysis ticker")
    if instrument.security_id is not None and not instrument.security_id.strip():
        raise StockSelectionUnavailableError("Instrument resolver returned an empty broker security ID")
    if resolution.resolved_at.tzinfo is None or resolution.resolved_at.utcoffset() is None:
        raise StockSelectionUnavailableError("Instrument resolver returned a timestamp without a timezone")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
