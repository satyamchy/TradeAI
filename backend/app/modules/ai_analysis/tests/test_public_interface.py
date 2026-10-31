from app.modules.ai_analysis.schemas import AnalysisDirection, AnalysisStatus
from app.modules.ai_analysis.service import AIAnalysisService


def test_analysis_contracts_and_interface_import_without_clients():
    assert AnalysisDirection.REVIEW.value == "REVIEW"
    assert AnalysisStatus.PENDING.value == "PENDING"
    assert callable(getattr(AIAnalysisService, "submit"))
