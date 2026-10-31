import subprocess
import sys

from app.modules.ai_analysis.schemas import AnalysisDirection, AnalysisStatus
from app.modules.ai_analysis.service import AIAnalysisService


def test_analysis_service_import_has_no_provider_client_side_effects():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from app.modules.ai_analysis import AIAnalysisService; "
            "assert 'tradingagents' not in sys.modules; "
            "assert 'langgraph' not in sys.modules; "
            "assert 'langchain_groq' not in sys.modules",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert AnalysisDirection.REVIEW.value == "REVIEW"
    assert AnalysisStatus.PENDING.value == "PENDING"
    assert callable(getattr(AIAnalysisService, "submit"))
