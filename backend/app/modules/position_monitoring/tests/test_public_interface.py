from app.modules.position_monitoring.schemas import PositionEvaluation
from app.modules.position_monitoring.service import PositionMonitoringService


def test_monitor_interface_returns_an_evaluation_contract():
    assert "action" in PositionEvaluation.model_fields
    assert callable(getattr(PositionMonitoringService, "evaluate"))
