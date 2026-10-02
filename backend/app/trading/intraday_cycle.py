"""One intraday pass: read the account, exit, then enter.

The pass places orders only through the trading gateway. Long entries buy
and later sell. Short entries sell and later buy back. Delivery positions
are closed on take-profit or stop-loss, and are left in place at the
15:15 intraday square-off. Exits run before new entries.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.trading.nifty50 import canonical_index, normalize_symbol
from app.trading.nse_session import (
    is_nse_cash_session_open,
    is_past_entry_cutoff,
    is_square_off_time,
    new_entries_blocked,
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

_WORKING = {"PENDING", "TRANSIT", "OPEN", "PART_TRADED"}
_FAILED = {"REJECTED", "CANCELLED", "EXPIRED", "FAILED", "UNKNOWN"}


async def run_intraday_cycle(
    gateway: Any,
    *,
    entries_enabled: bool,
    methods: list[str],
    limits: RiskLimits,
    now: datetime | None = None,
    force_square_off: bool = False,
    trading_index: str = "NIFTY 50",
    allowed_symbols: set[str] | None = None,
) -> dict:
    """Run one pass and return a snapshot the API can show.

    `now` overrides the clock so a closed session or the 15:15 flatten can
    be tested without waiting. `force_square_off` closes every open
    intraday position even when the clock has not reached 15:15. It does
    not send orders when the cash session is closed.
    """
    moment = now or now_ist()
    session_open = is_nse_cash_session_open(moment)
    past_cutoff = is_past_entry_cutoff(moment)
    square_off_due = force_square_off or (session_open and is_square_off_time(moment))
    index_name = canonical_index(trading_index)

    positions = await gateway.get_open_positions()
    realized = await gateway.realized_pnl_today_inr()
    prices = await _marks(gateway, [position["symbol"] for position in positions])
    unrealized = 0.0
    for position in positions:
        marked = prices.get(normalize_symbol(position["symbol"]))
        if marked:
            position["last_price"] = marked
            await gateway.set_last_price(
                position["symbol"], marked, position.get("product_type") or "INTRADAY"
            )
        position["pnl_percent"] = round(
            unrealized_pnl_percent(
                float(position["average_price"]),
                float(position["last_price"]),
                int(position["quantity"]),
            ),
            2,
        )
        unrealized += _rupee_pnl(position)

    loss_halt = daily_loss_halt(realized, limits.max_daily_loss_inr, unrealized)
    if loss_halt:
        square_off_due = True

    intraday = [row for row in positions if row.get("product_type", "INTRADAY") == "INTRADAY"]
    exits = await _exit_positions(
        gateway,
        positions,
        limits=limits,
        square_off_due=square_off_due,
        session_open=session_open,
    )

    positions = await gateway.get_open_positions()
    intraday = [row for row in positions if row.get("product_type", "INTRADAY") == "INTRADAY"]
    balance = await gateway.get_available_balance_inr()
    held = {normalize_symbol(position["symbol"]) for position in positions}
    working = await _working_symbols(gateway)
    held |= working

    candidates: dict[str, list[dict]] = {"intraday_long": [], "intraday_short": []}
    may_enter = (
        entries_enabled
        and session_open
        and not past_cutoff
        and not square_off_due
        and not loss_halt
        and not new_entries_blocked()
    )
    if may_enter:
        if "intraday_long" in methods:
            candidates["intraday_long"] = await rank_nifty50(
                "long", exclude=held, limit=limits.screener_limit, index=index_name
            )
        if "intraday_short" in methods:
            candidates["intraday_short"] = await rank_nifty50(
                "short", exclude=held, limit=limits.screener_limit, index=index_name
            )
        await _overlay_quotes(gateway, candidates)

    plan = []
    if may_enter:
        plan = build_entry_plan(
            balance_inr=balance,
            open_position_count=len(intraday),
            candidates_by_method=candidates,
            limits=limits,
        )

    rejections: list[dict] = []
    entries: list[dict] = []
    open_count = len(intraday)
    for item in plan:
        if item["symbol"] in working:
            rejections.append({**item, "reason": "an order in this symbol is still working"})
            continue
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
            allowed_symbols=allowed_symbols,
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
        if _order_failed(placed):
            entries.append({**item, "security_id": security_id, "status": "FAILED", "order": placed})
            continue
        filled = str(placed.get("status") or "").upper() in {"TRADED", "FILLED"}
        arm = getattr(gateway, "arm_protective_stop", None)
        if arm and filled:
            try:
                await arm(
                    item["symbol"],
                    security_id,
                    item["side"],
                    item["quantity"],
                    item["price"],
                    "INTRADAY",
                    limits.stop_loss_pct,
                )
            except Exception as exc:
                logger.warning("stop not parked for %s: %s", item["symbol"], exc)
        open_count += 1
        balance -= float(item["quantity"]) * float(item["price"])
        entries.append({**item, "security_id": security_id, "status": "PLACED", "order": placed})

    return {
        "ran_at_ist": moment.isoformat(),
        "entries_enabled": entries_enabled,
        "methods": list(methods),
        "trading_index": index_name,
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


async def _exit_positions(
    gateway: Any,
    positions: list[dict],
    *,
    limits: RiskLimits,
    square_off_due: bool,
    session_open: bool,
) -> list[dict]:
    planned = mark_positions_to_exit(
        positions,
        take_profit_pct=limits.take_profit_pct,
        stop_loss_pct=limits.stop_loss_pct,
        force_square_off=square_off_due,
    )
    exits: list[dict] = []
    for item in planned:
        if not session_open:
            exits.append({**_public_exit(item), "status": "FAILED", "error": "NSE cash session is closed"})
            continue
        fresh = await gateway.get_open_positions()
        product = item.get("product_type") or "INTRADAY"
        current = next(
            (
                row
                for row in fresh
                if normalize_symbol(row["symbol"]) == normalize_symbol(item["symbol"])
                and (row.get("product_type") or "INTRADAY") == product
            ),
            None,
        )
        if current is None or int(current["quantity"]) == 0:
            continue
        quantity = abs(int(current["quantity"]))
        side = "SELL" if int(current["quantity"]) > 0 else "BUY"
        cancel = getattr(gateway, "cancel_protective_stops", None)
        if cancel:
            try:
                await cancel(item["symbol"], product)
            except Exception as exc:
                logger.warning("stop cancel failed for %s: %s", item["symbol"], exc)
        security_id = current.get("security_id") or await gateway.resolve_security_id(item["symbol"])
        price = float(current.get("last_price") or item.get("last_price") or current.get("average_price") or 0)
        if not security_id or price <= 0:
            exits.append({**_public_exit(item), "status": "FAILED", "error": "missing security id or price"})
            continue
        try:
            placed = await gateway.place_intraday_order(
                item["symbol"],
                security_id,
                side,
                quantity,
                price,
                product,
            )
        except Exception as exc:
            logger.warning("exit failed for %s: %s", item["symbol"], exc)
            exits.append({**_public_exit(item), "status": "FAILED", "error": str(exc)})
            continue
        if _order_failed(placed):
            exits.append({**_public_exit(item), "status": "FAILED", "order": placed})
            continue
        public = _public_exit(item)
        public["side"] = side
        public["quantity"] = quantity
        exits.append({**public, "status": "PLACED", "order": placed})
    return exits


async def _marks(gateway: Any, symbols: list[str]) -> dict[str, float]:
    quote = getattr(gateway, "quote_prices", None)
    if quote is not None:
        try:
            quoted = await quote(symbols)
        except Exception as exc:
            logger.warning("quote failed: %s", exc)
            quoted = {}
        if quoted:
            return quoted
    return await last_traded_prices(symbols)


async def _overlay_quotes(gateway: Any, candidates: dict[str, list[dict]]) -> None:
    symbols = [row["symbol"] for rows in candidates.values() for row in rows]
    if not symbols:
        return
    prices = await _marks(gateway, symbols)
    for rows in candidates.values():
        for row in rows:
            marked = prices.get(normalize_symbol(row["symbol"]))
            if marked:
                row["ltp"] = marked


async def _working_symbols(gateway: Any) -> set[str]:
    getter = getattr(gateway, "get_orders", None)
    if getter is None:
        return set()
    try:
        orders = await getter()
    except Exception:
        return set()
    return {
        normalize_symbol(str(order.get("symbol") or ""))
        for order in orders
        if str(order.get("status") or "").upper() in _WORKING and order.get("symbol")
    }


def _order_failed(placed: dict) -> bool:
    return str(placed.get("status") or "").upper() in _FAILED


def _rupee_pnl(position: dict) -> float:
    quantity = int(position["quantity"])
    average = float(position["average_price"])
    last = float(position["last_price"])
    if quantity > 0:
        return (last - average) * quantity
    if quantity < 0:
        return (average - last) * abs(quantity)
    return 0.0


def _public_exit(item: dict) -> dict:
    return {
        "symbol": item["symbol"],
        "side": item["side"],
        "quantity": int(item["quantity_to_close"]),
        "price": float(item["last_price"]),
        "pnl_percent": item["pnl_percent"],
        "exit_reason": item["exit_reason"],
        "product_type": item.get("product_type") or "INTRADAY",
    }
