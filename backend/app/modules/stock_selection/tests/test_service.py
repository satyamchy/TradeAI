import asyncio

import pytest

from app.modules.stock_selection.instrument_master import AmbiguousInstrumentError, LocalNseInstrumentResolver
from app.modules.stock_selection.repository import SqlAlchemyCandidateRepository
from app.modules.stock_selection.schemas import CandidateFilters, RankCandidatesRequest, RankedCandidate
from app.modules.stock_selection.service import (
    CandidateNotFoundError,
    StockSelectionService,
    UnsupportedSelectionError,
)
from app.shared.contracts import (
    AnalysisHorizon,
    CandidateBatchStatus,
    CandidateRejectionCode,
    CandidateValidationStatus,
    CreateCandidatesRequest,
    SelectionMode,
)


def manual_request(symbols, *, exchange="NSE", mode=SelectionMode.MANUAL):
    return CreateCandidatesRequest(
        selection_mode=mode,
        symbols=symbols,
        horizon=AnalysisHorizon.INTRADAY,
        exchange=exchange,
    )


def make_service(candidate_store, resolver=None, ranking_provider=None):
    return StockSelectionService(
        SqlAlchemyCandidateRepository(candidate_store),
        resolver or LocalNseInstrumentResolver(),
        ranking_provider,
    )


def test_manual_candidates_normalize_and_report_duplicates_and_unknowns(candidate_store):
    service = make_service(candidate_store)

    batch = asyncio.run(
        service.create_candidates(
            manual_request([" reliance ", "RELIANCE.NS", "NOTASYMBOL"]),
            owner_id=1,
        )
    )

    assert batch.status is CandidateBatchStatus.PARTIAL
    assert len(batch.candidates) == 1
    assert batch.candidates[0].instrument.symbol == "RELIANCE"
    assert batch.candidates[0].instrument.analysis_ticker == "RELIANCE.NS"
    assert batch.candidates[0].instrument.security_id is None
    assert batch.candidates[0].validation_status is CandidateValidationStatus.ANALYSIS_ONLY
    assert [item.code for item in batch.rejections] == [
        CandidateRejectionCode.DUPLICATE_SYMBOL,
        CandidateRejectionCode.UNKNOWN_SYMBOL,
    ]
    assert batch.rejected_symbols == ["RELIANCE.NS", "NOTASYMBOL"]


def test_invalid_and_empty_symbols_are_explicitly_rejected(candidate_store):
    service = make_service(candidate_store)

    batch = asyncio.run(service.create_candidates(manual_request(["   ", "RE LIANCE", "TCS.BO"])))

    assert batch.status is CandidateBatchStatus.REJECTED
    assert batch.candidates == []
    assert [rejection.code for rejection in batch.rejections] == [
        CandidateRejectionCode.EMPTY_SYMBOL,
        CandidateRejectionCode.INVALID_SYMBOL,
        CandidateRejectionCode.INVALID_SYMBOL,
    ]


def test_ambiguous_instrument_is_reported_without_creating_a_candidate(candidate_store):
    class AmbiguousResolver:
        def resolve(self, symbol, exchange):
            raise AmbiguousInstrumentError(symbol)

    batch = asyncio.run(make_service(candidate_store, AmbiguousResolver()).create_candidates(
        manual_request(["RELIANCE"])
    ))

    assert batch.status is CandidateBatchStatus.REJECTED
    assert batch.rejections[0].code is CandidateRejectionCode.AMBIGUOUS_SYMBOL


def test_scanner_mode_and_non_nse_exchange_are_not_silently_accepted(candidate_store):
    service = make_service(candidate_store)

    with pytest.raises(UnsupportedSelectionError):
        asyncio.run(service.create_candidates(manual_request(["RELIANCE"], mode=SelectionMode.TOP_GAINERS)))
    with pytest.raises(UnsupportedSelectionError):
        asyncio.run(service.create_candidates(manual_request(["RELIANCE"], exchange="BSE")))


def test_persisted_candidates_can_be_reloaded_and_are_owner_scoped(candidate_store):
    service = make_service(candidate_store)
    batch = asyncio.run(service.create_candidates(manual_request(["TCS"]), owner_id=1))
    candidate_id = batch.candidates[0].candidate_id

    loaded = asyncio.run(service.get_candidate(candidate_id, owner_id=1))
    own_list = asyncio.run(service.list_candidates(CandidateFilters(horizon="INTRADAY"), owner_id=1))
    other_list = asyncio.run(service.list_candidates(CandidateFilters(), owner_id=2))

    assert loaded.candidate_id == candidate_id
    assert loaded.batch_id == batch.batch_id
    assert loaded.selection_reason == "USER_SELECTED"
    assert loaded.mapping_source == "LEGACY_NIFTY50_FALLBACK"
    assert own_list == [loaded]
    assert other_list == []
    with pytest.raises(CandidateNotFoundError):
        asyncio.run(service.get_candidate(candidate_id, owner_id=2))


def test_batches_with_only_rejections_are_still_persisted(candidate_store):
    service = make_service(candidate_store)

    batch = asyncio.run(service.create_candidates(manual_request(["UNKNOWN"]), owner_id=1))
    listed = asyncio.run(service.list_candidates(CandidateFilters(), owner_id=1))

    assert batch.status is CandidateBatchStatus.REJECTED
    assert listed == []


def test_existing_screener_is_exposed_as_typed_module_service(candidate_store):
    class FakeRankingProvider:
        async def rank(self, request):
            assert request.side == "long"
            return [RankedCandidate(symbol="TCS", ltp=10, score=1)]

    service = make_service(candidate_store, ranking_provider=FakeRankingProvider())
    ranked = asyncio.run(service.rank_candidates(RankCandidatesRequest(side="long")))

    assert ranked == [RankedCandidate(symbol="TCS", ltp=10, score=1)]
