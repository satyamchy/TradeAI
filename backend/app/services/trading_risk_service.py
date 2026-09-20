import logging
from dataclasses import dataclass

from app.integrations.dhan.client import get_dhan_client
from app.services.market_data_service import get_indian_market_status

logger = logging.getLogger(__name__)

MAX_CAPITAL_PER_TRADE = 10_000.0
MAX_OPEN_POSITIONS = 5


@dataclass
class RiskCheckResult:
    passed: bool
    reason: str


async def get_available_funds() -> float:
    """dhan.get_fund_limits() returns a dict-like payload with 'availabelBalance'
    (note: Dhan's actual field is misspelled in their API response)."""
    dhan = get_dhan_client()
    resp = dhan.get_fund_limits()
    if resp.get("status") != "success" and "data" not in resp:
        raise RuntimeError(f"get_fund_limits failed: {resp}")
    data = resp.get("data", resp)
    balance = data.get("availabelBalance") or data.get("availableBalance") or data.get("sodLimit")
    if balance is None:
        raise RuntimeError(f"Could not find balance field in fund limits response: {data}")
    return float(balance)


async def get_open_position_count() -> int:
    dhan = get_dhan_client()
    resp = dhan.get_positions()
    positions = resp.get("data", resp) if isinstance(resp, dict) else resp
    if not isinstance(positions, list):
        return 0
    return len([p for p in positions if float(p.get("netQty", 0)) != 0])


async def has_open_position(security_id: str) -> bool:
    dhan = get_dhan_client()
    resp = dhan.get_positions()
    positions = resp.get("data", resp) if isinstance(resp, dict) else resp
    if not isinstance(positions, list):
        return False
    return any(str(p.get("securityId")) == str(security_id) and float(p.get("netQty", 0)) != 0 for p in positions)


async def run_risk_checks(entry_price_cap: float, quantity: int, trade_type: str, security_id: str) -> RiskCheckResult:
    market_status = get_indian_market_status()
    if not market_status["is_open"]:
        return RiskCheckResult(False, f"Market is not open ({market_status['message']})")

    if trade_type == "INTRADAY" and market_status["current_time_ist"][11:16] > "15:00":
        return RiskCheckResult(False, "Too close to market close to open a new intraday position")

    estimated_cost = entry_price_cap * quantity
    if estimated_cost > MAX_CAPITAL_PER_TRADE:
        return RiskCheckResult(False, f"Order cost ₹{estimated_cost:.2f} exceeds per-trade cap ₹{MAX_CAPITAL_PER_TRADE}")

    try:
        available = await get_available_funds()
    except Exception as e:
        logger.error("Funds check failed: %s", e, exc_info=True)
        return RiskCheckResult(False, f"Could not verify available funds, refusing order: {e}")
    if available < estimated_cost:
        return RiskCheckResult(False, f"Insufficient funds: available ₹{available:.2f}, need ₹{estimated_cost:.2f}")

    try:
        if await has_open_position(security_id):
            return RiskCheckResult(False, "Already holding an open position in this instrument")
        open_positions = await get_open_position_count()
    except Exception as e:
        logger.error("Position check failed: %s", e, exc_info=True)
        return RiskCheckResult(False, f"Could not verify open positions, refusing order: {e}")
    if open_positions >= MAX_OPEN_POSITIONS:
        return RiskCheckResult(False, f"Max open positions ({MAX_OPEN_POSITIONS}) already reached")

    return RiskCheckResult(True, "All checks passed")