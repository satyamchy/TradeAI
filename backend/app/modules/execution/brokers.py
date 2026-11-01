"""Adapters for the single existing TradingGateway execution path."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol

from app.modules.execution.schemas import BrokerOrderUpdate
from app.shared.contracts import ApprovedOrderIntent, ExecutionMode, ExecutionResult


class TradingGatewayPort(Protocol):
    mode: str

    async def place_tagged_order(
        self, symbol: str, security_id: str, side: str, quantity: int,
        price: float, product_type: str, tag: str,
    ) -> dict: ...

    async def poll_order(self, order_id: str, *, tag: str | None = None) -> dict: ...
    async def cancel_order(self, order_id: str) -> dict: ...


class ExistingTradingGatewayAdapter:
    """Wrap the app's one `TradingGateway`; this adapter never constructs it."""

    def __init__(self, gateway: TradingGatewayPort):
        self._gateway = gateway

    @property
    def name(self) -> str:
        return "dhan" if self._gateway.mode.lower() == "live" else "paper"

    async def submit(self, intent: ApprovedOrderIntent, *, mode: ExecutionMode) -> BrokerOrderUpdate:
        if self._gateway.mode.lower() != mode.value.lower():
            raise RuntimeError("execution mode does not match the configured TradingGateway")
        reference_price = intent.reference_price or intent.limit_price
        if reference_price is None:
            raise ValueError("market order requires a reference price for paper execution")
        tag = _broker_tag(intent.idempotency_key)
        try:
            raw = await self._gateway.place_tagged_order(
                symbol=intent.symbol,
                security_id=intent.security_id,
                side=intent.side.value,
                quantity=intent.quantity,
                price=float(reference_price),
                product_type=intent.product_type,
                tag=tag,
            )
        except Exception as exc:
            # The existing paper ledger reports known validation/capital
            # failures before writing a fill. Translate those into a terminal
            # broker rejection; other failures remain UNKNOWN in Module 4.
            from app.broker.paper_ledger import PaperLedgerError

            if mode is not ExecutionMode.PAPER or not isinstance(exc, PaperLedgerError):
                raise
            return BrokerOrderUpdate(
                broker=self.name,
                status="REJECTED",
                broker_order_id=None,
                filled_quantity=0,
                average_fill_price=None,
                updated_at=datetime.now(timezone.utc),
                rejection_reason=str(exc),
            )
        return _update(raw)

    async def get_order_status(self, order: ExecutionResult) -> BrokerOrderUpdate:
        raw = await self._gateway.poll_order(
            order.broker_order_id or "", tag=_broker_tag(order.idempotency_key)
        )
        return _update(raw)

    async def cancel_order(self, order: ExecutionResult) -> BrokerOrderUpdate:
        if not order.broker_order_id:
            return BrokerOrderUpdate(
                broker=self.name,
                status="UNKNOWN",
                broker_order_id=None,
                filled_quantity=order.filled_quantity,
                average_fill_price=order.average_fill_price,
                updated_at=datetime.now(timezone.utc),
            )
        raw = await self._gateway.cancel_order(order.broker_order_id)
        return _update(raw)


def _update(raw: dict) -> BrokerOrderUpdate:
    if not isinstance(raw, dict):
        raise ValueError("broker adapter returned a non-object response")
    broker = str(raw.get("broker") or "unknown")[:32]
    status = str(raw.get("status") or raw.get("order_status") or raw.get("orderStatus") or "UNKNOWN")[:32]
    broker_order_id = raw.get("broker_order_id") or raw.get("order_id") or raw.get("orderId")
    filled_raw = raw.get(
        "filled_quantity",
        raw.get(
            "traded_quantity",
            raw.get("filledQty", raw.get("tradedQuantity", raw.get("quantity", 0) if status.upper() in {"FILLED", "TRADED"} else 0)),
        ),
    )
    filled = int(float(filled_raw or 0))
    price_raw = raw.get("average_fill_price", raw.get("average_price", raw.get("averageTradedPrice", raw.get("price"))))
    average_price = Decimal(str(price_raw)) if price_raw not in (None, "", 0, "0") else None
    return BrokerOrderUpdate(
        broker=broker,
        status=status,
        broker_order_id=str(broker_order_id) if broker_order_id else None,
        filled_quantity=filled,
        average_fill_price=average_price,
        updated_at=_parse_time(raw.get("updated_at") or raw.get("updateTime")),
        rejection_reason=raw.get("rejection_reason") or raw.get("remarks") or raw.get("message"),
    )


def _parse_time(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _broker_tag(idempotency_key: str) -> str:
    """Keep a compact correlation tag suitable for the existing Dhan adapter."""
    import hashlib

    return hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:16]
