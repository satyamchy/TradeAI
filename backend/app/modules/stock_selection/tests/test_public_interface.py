import subprocess
import sys

from app.modules.stock_selection import CreateCandidatesRequest, StockSelectionService
from app.shared.contracts import AnalysisHorizon, SelectionMode


def test_public_service_import_has_no_broker_or_ai_client_side_effects():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from app.modules.stock_selection import StockSelectionService; "
            "assert 'app.broker.dhan_gateway' not in sys.modules; "
            "assert 'tradingagents' not in sys.modules; "
            "assert 'langgraph' not in sys.modules",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    request = CreateCandidatesRequest(
        selection_mode=SelectionMode.MANUAL,
        symbols=["RELIANCE"],
        horizon=AnalysisHorizon.INTRADAY,
    )
    assert request.symbols == ["RELIANCE"]
    assert callable(getattr(StockSelectionService, "create_candidates"))
