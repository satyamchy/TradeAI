"""Deterministic position health and exit-candidate evaluation."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol, Sequence
from uuid import UUID

from app.modules.position_monitoring.repository import TriggerRepository
from app.modules.position_monitoring.schemas import PositionMonitorInput
from app.shared.contracts import PositionEvaluation, PositionStatus


class PositionMonitoringServiceProtocol(Protocol):
    def evaluate(self, position: PositionMonitorInput) -> PositionEvaluation: ...
    def evaluate_open_positions(self, positions: Sequence[PositionMonitorInput]) -> list[PositionEvaluation]: ...


class PositionMonitoringService:
    """Evaluates confirmed filled quantity and returns candidates only."""

    def __init__(self, *, triggers: TriggerRepository, clock=lambda: datetime.now(timezone.utc)) -> None:
        self._triggers = triggers
        self._clock = clock

    def evaluate(self, position: PositionMonitorInput) -> PositionEvaluation:
        now = _aware(self._clock())
        current_price = position.market.price
        captured_at = position.market.captured_at
        pnl = _unrealized_pnl(position.average_price, current_price, position.confirmed_open_quantity)

        if position.status not in {PositionStatus.OPEN, PositionStatus.PARTIALLY_CLOSED}:
            return PositionEvaluation(
                position_id=position.position_id,
                symbol=position.symbol,
                status=position.status,
                action="HOLD",
                current_price=current_price,
                unrealized_pnl=pnl,
                market_data_at=captured_at,
            )

        reason = _determine_trigger(position, now)
        if reason == "SESSION_SQUARE_OFF":
            trigger_id, is_new = self._triggers.record_trigger(
                position_id=position.position_id,
                reason=reason,
                policy_version=position.rules.version,
                price=current_price,
                occurred_at=now,
            )
            return PositionEvaluation(
                position_id=position.position_id,
                symbol=position.symbol,
                status=position.status,
                action="EXIT_CANDIDATE",
                current_price=current_price,
                unrealized_pnl=pnl,
                trigger_reason=reason,
                market_data_at=captured_at,
                trigger_id=trigger_id,
                exit_quantity=position.confirmed_open_quantity,
                is_new_trigger=is_new,
            )

        feed_problem = _feed_problem(position, now)
        if feed_problem:
            return PositionEvaluation(
                position_id=position.position_id,
                symbol=position.symbol,
                status=PositionStatus.DATA_UNAVAILABLE,
                action="DATA_UNAVAILABLE",
                current_price=current_price,
                unrealized_pnl=None,
                trigger_reason=feed_problem,
                market_data_at=captured_at,
            )

        reason = _determine_price_trigger(position)
        if reason is None:
            return PositionEvaluation(
                position_id=position.position_id,
                symbol=position.symbol,
                status=position.status,
                action="HOLD",
                current_price=current_price,
                unrealized_pnl=pnl,
                market_data_at=captured_at,
            )

        trigger_id, is_new = self._triggers.record_trigger(
            position_id=position.position_id,
            reason=reason,
            policy_version=position.rules.version,
            price=current_price,
            occurred_at=now,
        )
        return PositionEvaluation(
            position_id=position.position_id,
            symbol=position.symbol,
            status=position.status,
            action="EXIT_CANDIDATE",
            current_price=current_price,
            unrealized_pnl=pnl,
            trigger_reason=reason,
            market_data_at=captured_at,
            trigger_id=trigger_id,
            exit_quantity=position.confirmed_open_quantity,
            is_new_trigger=is_new,
        )

    def evaluate_open_positions(self, positions: Sequence[PositionMonitorInput]) -> list[PositionEvaluation]:
        """Evaluate supplied confirmed positions; caller owns scheduling and data loading."""
        return [self.evaluate(position) for position in positions]


def _determine_trigger(position: PositionMonitorInput, now: datetime) -> str | None:
    square_off_at = position.rules.square_off_at
    if square_off_at is not None and now >= _aware(square_off_at):
        return "SESSION_SQUARE_OFF"
    return None


def _feed_problem(position: PositionMonitorInput, now: datetime) -> str | None:
    observation = position.market
    if observation.price is None or observation.captured_at is None:
        return "MARKET_DATA_MISSING"
    age = (now - _aware(observation.captured_at)).total_seconds()
    if age < -30 or age > position.rules.max_market_age_seconds:
        return "MARKET_DATA_STALE"
    if not observation.market_open:
        return "MARKET_CLOSED"
    return None


def _determine_price_trigger(position: PositionMonitorInput) -> str | None:
    price = position.market.price
    assert price is not None
    stop = position.rules.stop_loss_price
    target = position.rules.target_price
    if stop is not None and price <= stop:
        return "STOP_LOSS"
    if target is not None and price >= target:
        return "TARGET_REACHED"
    return None


def _unrealized_pnl(average: Decimal, current: Decimal | None, quantity: int) -> Decimal | None:
    if current is None:
        return None
    return (current - average) * quantity


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("monitor timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)
