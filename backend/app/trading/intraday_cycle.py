"""One intraday pass: read the account, screen, enter, and exit.

The pass places orders only through the trading gateway. Long entries buy
and later sell. Short entries sell and later buy back. Both use the same
exit rules.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.trading.nifty50 import normalize_symbol
from app.trading.nse_session import (
    is_nse_cash_session_open,
    is_past_entry_cutoff,
    is_square_off_time,
    now_ist,
)
from app.trading.risk_limits import (
    RiskLimits,
    build_entry_plan,
    check_new_entry,
    daily_loss_halt,
    mark_positions_to_exit,
    unrealized_pnl_percent,
)
from app.trading.screener import last_traded_prices, rank_nifty50
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def run_intraday_cycle(
    gateway: Any,
    *,
    entries_enabled: bool,
    methods: list[str],
    limits: RiskLimits,
    now: datetime | None = None,
    force_square_off: bool = False,
) -> dict:
    """Run one pass and return a snapshot the API can show.

    `now` overrides the clock so a closed session or the 15:15 flatten can
    be tested without waiting. `force_square_off` closes every open
    intraday position even outside the session.
    """
    moment = now or now_ist()
    session_open = is_nse_cash_session_open(moment)
    past_cutoff = is_past_entry_cutoff(moment)
    square_off_due = force_square_off or (session_open and is_square_off_time(moment))

    positions = await gateway.get_open_positions()
    positions = [row for row in positions if row.get("product_type", "INTRADAY") == "INTRADAY"]
    realized = await gateway.realized_pnl_today_inr()
    loss_halt = daily_loss_halt(realized, limits.max_daily_loss_inr)
    if loss_halt:
        square_off_due = True

    prices = await last_traded_prices([position["symbol"] for position in positions])
    for position in positions:
        marked = prices.get(normalize_symbol(position["symbol"]))
        if marked:
            position["last_price"] = marked
            await gateway.set_last_price(position["symbol"], marked)
        position["pnl_percent"] = round(
            unrealized_pnl_percent(
                float(position["average_price"]),
                float(position["last_price"]),
                int(position["quantity"]),
            ),
            2,
        )

    balance = await gateway.get_available_balance_inr()
    held = {normalize_symbol(position["symbol"]) for position in positions}
    candidates: dict[str, list[dict]] = {"intraday_long": [], "intraday_short": []}
    may_enter = (
        entries_enabled
        and session_open
        and not past_cutoff
        and not square_off_due
        and not loss_halt
    )
    if may_enter:
        if "intraday_long" in methods:
            candidates["intraday_long"] = await rank_nifty50("long", exclude=held, limit=limits.screener_limit)
        if "intraday_short" in methods:
            candidates["intraday_short"] = await rank_nifty50("short", exclude=held, limit=limits.screener_limit)

    plan = []
    if may_enter:
        plan = build_entry_plan(
            balance_inr=balance,
            open_position_count=len(positions),
            candidates_by_method=candidates,
            limits=limits,
        )

    rejections: list[dict] = []
    entries: list[dict] = []
    open_count = len(positions)
    for item in plan:
        security_id = await gateway.resolve_security_id(item["symbol"])
        reason = check_new_entry(
            symbol=item["symbol"],
            security_id=security_id,
            side=item["side"],
            quantity=item["quantity"],
            price=item["price"],
            balance_inr=balance,
            open_position_count=open_count,
            limits=limits,
            session_open=session_open,
            past_entry_cutoff=past_cutoff,
            square_off_due=square_off_due,
            daily_loss_halt=loss_halt,
        )
        if reason:
            rejections.append({**item, "reason": reason})
            continue
        try:
            placed = await gateway.place_intraday_order(
                item["symbol"],
                security_id,
                item["side"],
                item["quantity"],
                item["price"],
            )
        except Exception as exc:
            logger.warning("entry failed for %s: %s", item["symbol"], exc)
            entries.append({**item, "security_id": security_id, "status": "FAILED", "error": str(exc)})
            continue
        open_count += 1
        entries.append({**item, "security_id": security_id, "status": "PLACED", "order": placed})

    # Exits use the positions read at the start of this pass, so a fill from
    # this pass is evaluated on the next one.
    exits_planned = mark_positions_to_exit(
        positions,
        take_profit_pct=limits.take_profit_pct,
        stop_loss_pct=limits.stop_loss_pct,
        force_square_off=square_off_due,
    )
    exits: list[dict] = []
    for item in exits_planned:
        security_id = item.get("security_id") or await gateway.resolve_security_id(item["symbol"])
        price = float(item["last_price"] or item["average_price"] or 0)
        if not security_id or price <= 0:
            exits.append({**_public_exit(item), "status": "FAILED", "error": "missing security id or price"})
            continue
        try:
            placed = await gateway.place_intraday_order(
                item["symbol"],
                security_id,
                item["side"],
                int(item["quantity_to_close"]),
                price,
            )
        except Exception as exc:
            logger.warning("exit failed for %s: %s", item["symbol"], exc)
            exits.append({**_public_exit(item), "status": "FAILED", "error": str(exc)})
            continue
        exits.append({**_public_exit(item), "status": "PLACED", "order": placed})

    return {
        "ran_at_ist": moment.isoformat(),
        "entries_enabled": entries_enabled,
        "methods": list(methods),
        "session_open": session_open,
        "past_entry_cutoff": past_cutoff,
        "square_off_due": square_off_due,
        "daily_loss_halt": loss_halt,
        "available_balance_inr": round(balance, 2),
        "candidates": candidates,
        "entry_plan": plan,
        "rejections": rejections,
        "entries": entries,
        "exits": exits,
    }


def _public_exit(item: dict) -> dict:
    return {
        "symbol": item["symbol"],
        "side": item["side"],
        "quantity": int(item["quantity_to_close"]),
        "price": float(item["last_price"]),
        "pnl_percent": item["pnl_percent"],
        "exit_reason": item["exit_reason"],
    }
