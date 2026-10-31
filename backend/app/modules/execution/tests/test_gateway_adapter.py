import asyncio
from decimal import Decimal

from app.modules.execution.brokers import ExistingTradingGatewayAdapter
from app.modules.execution.tests.conftest import NOW
from app.shared.contracts import ExecutionMode


class FakeExistingTradingGateway:
    mode = "paper"

    def __init__(self):
        self.submissions = []

    async def place_tagged_order(self, **payload):
        self.submissions.append(payload)
        return {
            "order_id": "paper-17", "broker": "paper", "status": "FILLED",
            "symbol": "RELIANCE", "side": "BUY", "quantity": 5,
            "price": 100.0, "product_type": "INTRADAY",
        }

    async def poll_order(self, order_id, *, tag=None):
        return {"order_id": order_id, "broker": "paper", "status": "FILLED", "traded_quantity": 5,
                "average_price": 100.0, "updated_at": NOW.isoformat()}

    async def cancel_order(self, order_id):
        return {"order_id": order_id, "broker": "paper", "status": "CANCELLED"}


def test_adapter_uses_the_injected_single_gateway_and_maps_filled_paper_order(execution_context):
    from app.modules.execution.tests.conftest import execution_request

    gateway = FakeExistingTradingGateway()
    adapter = ExistingTradingGatewayAdapter(gateway)
    intent = execution_context["intent"]
    result = asyncio.run(adapter.submit(intent, mode=ExecutionMode.PAPER))

    assert adapter.name == "paper"
    assert result.status == "FILLED"
    assert result.filled_quantity == 5
    assert result.average_fill_price == Decimal("100.0")
    assert gateway.submissions[0]["security_id"] == "2885"
    assert gateway.submissions[0]["side"] == "BUY"
    assert gateway.submissions[0]["product_type"] == "INTRADAY"
    assert len(gateway.submissions[0]["tag"]) == 16

