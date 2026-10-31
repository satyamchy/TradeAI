from app.modules.execution.schemas import ExecutionMode, ExecutionRequest
from app.modules.execution.service import ExecutionService
from uuid import uuid4


def test_execution_contract_requires_intent_reference_and_mode():
    request = ExecutionRequest(order_intent_id=uuid4(), execution_mode=ExecutionMode.PAPER)

    assert request.execution_mode is ExecutionMode.PAPER
    assert callable(getattr(ExecutionService, "execute"))
