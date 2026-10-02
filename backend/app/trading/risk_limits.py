"""Hard limits checked before an entry, and the rules that mark an exit.

Nothing here calls the broker. Prices are INR per share. Percents are
plain numbers: 1.5 means 1.5 percent. Quantity is signed shares.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.trading.nifty50 import is_nifty50_symbol, normalize_symbol


@dataclass
class RiskLimits:
    """Limits for one process. The runner can replace this object while running."""

    max_positions: int
    capital_per_trade_pct: float
    cash_reserve_pct: float
    take_profit_pct: float
    stop_loss_pct: float
    max_daily_loss_inr: float
    screener_limit: int
    cycle_interval_seconds: int


def unrealized_pnl_percent(average_price: float, last_price: float, quantity: int) -> float:
    """Open profit as a percent of the average price.

    Long quantity is positive: (last - average) / average * 100.
    Short quantity is negative: (average - last) / average * 100.
    A short uses the inverted move because it profits when the price falls.
    """
    if average_price <= 0 or quantity == 0:
        return 0.0
    if quantity > 0:
        return (last_price - average_price) / average_price * 100
    return (average_price - last_price) / average_price * 100


def check_new_entry(
    *,
    symbol: str,
    security_id: str | None,
    side: str,
    quantity: int,
    price: float,
    balance_inr: float,
    open_position_count: int,
    limits: RiskLimits,
    session_open: bool,
    past_entry_cutoff: bool,
    square_off_due: bool,
    daily_loss_halt: bool,
    product_type: str = "INTRADAY",
    allowed_symbols: set[str] | None = None,
) -> str | None:
    """Return a rejection reason, or None when the entry may be sent.

    `price` and `balance_inr` are INR. `quantity` is a positive share count.
    The per-trade cap and the cash reserve are both measured against `balance_inr`.
    """
    if not session_open:
        return "NSE cash session is closed"
    if product_type == "INTRADAY" and square_off_due:
        return "square-off time has passed"
    if product_type == "INTRADAY" and past_entry_cutoff:
        return "new entries stop at 14:45 IST"
    if daily_loss_halt:
        return "daily loss limit is hit"
    if product_type == "INTRADAY" and open_position_count >= limits.max_positions:
        return "max open positions is reached"
    universe = allowed_symbols if allowed_symbols is not None else None
    if universe is not None:
        if normalize_symbol(symbol) not in universe:
            return "symbol is not in the selected index"
    elif not is_nifty50_symbol(symbol):
        return "symbol is not in the NIFTY 50 list"
    if not security_id:
        return "Dhan security id is missing"
    if side not in {"BUY", "SELL"}:
        return "side must be BUY or SELL"
    if quantity < 1:
        return "quantity is below 1 share"
    if price <= 0:
        return "price must be greater than 0"
    notional = round(price * quantity, 2)
    trade_cap = round(balance_inr * limits.capital_per_trade_pct, 2)
    spendable = round(balance_inr * (1 - limits.cash_reserve_pct), 2)
    if notional > trade_cap:
        return "order is above the per-trade cash cap"
    if notional > spendable:
        return "order would spend the cash reserve"
    return None


def build_entry_plan(
    *,
    balance_inr: float,
    open_position_count: int,
    candidates_by_method: dict[str, list[dict]],
    limits: RiskLimits,
) -> list[dict]:
    """Size orders from spendable cash.

    Each candidate needs `symbol` and `ltp` in INR. The plan does not
    resolve security ids. Slots and the per-trade cap are shared by the
    long and short methods. Long names are sized first.
    """
    open_slots = limits.max_positions - open_position_count
    if open_slots <= 0 or balance_inr <= 0:
        return []

    spendable = balance_inr * (1 - limits.cash_reserve_pct)
    per_trade_cap = balance_inr * limits.capital_per_trade_pct
    remaining = spendable
    plan: list[dict] = []

    ordered: list[tuple[str, dict]] = []
    for method in ("intraday_long", "intraday_short"):
        for candidate in candidates_by_method.get(method, []):
            ordered.append((method, candidate))

    for method, candidate in ordered:
        if len(plan) >= open_slots or remaining <= 0:
            break
        price = float(candidate.get("ltp") or 0)
        if price <= 0:
            continue
        allocation = min(per_trade_cap, remaining)
        quantity = int(allocation // price)
        if quantity < 1:
            continue
        cost = quantity * price
        plan.append(
            {
                "symbol": normalize_symbol(candidate["symbol"]),
                "method": method,
                "side": "BUY" if method == "intraday_long" else "SELL",
                "quantity": quantity,
                "price": price,
                "allocated_amount_inr": round(cost, 2),
            }
        )
        remaining -= cost
    return plan


def mark_positions_to_exit(
    positions: list[dict],
    *,
    take_profit_pct: float,
    stop_loss_pct: float,
    force_square_off: bool,
) -> list[dict]:
    """Positions that should be closed on this pass.

    Each position needs signed `quantity`, `average_price`, and `last_price`
    in INR. A forced square-off closes every open intraday position.
    Otherwise a long or a short closes at the take-profit or stop-loss percent.
    """
    exits = []
    for position in positions:
        quantity = int(position["quantity"])
        if quantity == 0:
            continue
        pnl_percent = unrealized_pnl_percent(
            float(position["average_price"]),
            float(position["last_price"]),
            quantity,
        )
        product = str(position.get("product_type") or "INTRADAY")
        reason = None
        # Delivery is not flattened on the clock. Intraday is.
        if force_square_off and product != "DELIVERY":
            reason = "square-off"
        elif pnl_percent >= take_profit_pct:
            reason = "take-profit"
        elif pnl_percent <= -stop_loss_pct:
            reason = "stop-loss"
        if reason is None:
            continue
        exits.append(
            {
                **position,
                "pnl_percent": round(pnl_percent, 2),
                "exit_reason": reason,
                "side": "SELL" if quantity > 0 else "BUY",
                "quantity_to_close": abs(quantity),
            }
        )
    return exits


def daily_loss_halt(
    realized_pnl_inr: float,
    max_daily_loss_inr: float,
    unrealized_pnl_inr: float = 0.0,
) -> bool:
    """True when today's realized plus open loss has reached the limit.

    Both P&L figures are negative for a loss. The limit is a positive INR amount.
    A later market flatten can still slip past the number; the broker stop bounds
    each position while this process is down.
    """
    return (realized_pnl_inr + unrealized_pnl_inr) <= -abs(max_daily_loss_inr)
