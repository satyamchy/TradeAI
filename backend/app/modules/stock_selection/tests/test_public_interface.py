from app.modules.stock_selection.schemas import CreateCandidatesRequest
from app.modules.stock_selection.service import StockSelectionService
from app.shared.contracts import AnalysisHorizon, SelectionMode


def test_contract_and_service_are_importable_without_provider_setup():
    request = CreateCandidatesRequest(
        selection_mode=SelectionMode.MANUAL,
        symbols=["RELIANCE"],
        horizon=AnalysisHorizon.INTRADAY,
    )

    assert request.symbols == ["RELIANCE"]
    assert callable(getattr(StockSelectionService, "create_candidates"))
