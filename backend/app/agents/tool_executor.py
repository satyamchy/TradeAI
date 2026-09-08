import asyncio
import datetime
import time
import uuid

from app.tools.registry import TOOLS
from app.agents.state import ConversationState
from app.utils.logger import get_logger
from app.db.base import AsyncSessionLocal
from app.db.models import ActivePosition


logger = get_logger(__name__)


async def _update_active_position_from_tool(output_data: dict, active_position_id: int = None, ticker: str = None):
    """Updates or records active position evaluation based on tool output."""
    if not isinstance(output_data, dict):
        return

    sym = output_data.get("ticker") or ticker
    if not sym:
        return

    cur_price = output_data.get("current_price")
    pivots = output_data.get("indicators", {}).get("pivot_points", {})
    target_price = pivots.get("r1") if pivots else None
    stop_loss = pivots.get("s1") if pivots else None

    # Derive recommendation based on indicators
    rsi = output_data.get("indicators", {}).get("rsi_14")
    recommendation = "HOLD"
    if rsi is not None:
        if rsi < 35:
            recommendation = "BUY"
        elif rsi > 70:
            recommendation = "SELL"

    try:
        async with AsyncSessionLocal() as session:
            pos = None
            if active_position_id:
                pos = await session.get(ActivePosition, active_position_id)
            if not pos and sym:
                # Look up by ticker if open
                from sqlalchemy.future import select
                res = await session.execute(
                    select(ActivePosition).where(ActivePosition.ticker == sym.upper())
                )
                pos = res.scalars().first()

            now = datetime.datetime.utcnow()
            reason = f"Evaluated via tool_executor at {now.isoformat()} UTC. Price={cur_price}, RSI={rsi}"

            if pos:
                if cur_price is not None:
                    pos.current_price = cur_price
                if target_price:
                    pos.target_price = target_price
                if stop_loss:
                    pos.stop_loss = stop_loss
                pos.recommendation = recommendation
                pos.evaluation_reason = reason
                pos.last_evaluated_at = now
                pos.status = "EVALUATED" if pos.status == "OPEN" else pos.status
                session.add(pos)
                await session.commit()
                logger.info("ACTIVE_POSITION_UPDATED | id=%s | ticker=%s | price=%s", pos.id, sym, cur_price)
            else:
                new_pos = ActivePosition(
                    ticker=sym.upper(),
                    symbol=sym.upper().replace(".NS", ""),
                    current_price=cur_price,
                    target_price=target_price,
                    stop_loss=stop_loss,
                    recommendation=recommendation,
                    status="EVALUATED",
                    evaluation_reason=reason,
                    last_evaluated_at=now,
                )
                session.add(new_pos)
                await session.commit()
                logger.info("ACTIVE_POSITION_CREATED | id=%s | ticker=%s | price=%s", new_pos.id, sym, cur_price)
    except Exception as exc:
        logger.warning("FAILED_UPDATE_ACTIVE_POSITION | ticker=%s | error=%s", sym, exc)


async def execute_tool(step, tool_call_id: str):
    tool_name = step.tool
    tool_input = step.input

    logger.info(
        "TOOL_CALL_START | id=%s | tool=%s | input=%s",
        tool_call_id,
        tool_name,
        tool_input,
    )

    start_time = time.perf_counter()

    try:
        tool = TOOLS.get(tool_name)

        if tool is None:
            logger.error(
                "TOOL_NOT_FOUND | id=%s | tool=%s",
                tool_call_id,
                tool_name,
            )

            return {
                "tool_call_id": tool_call_id,
                "tool": tool_name,
                "input": tool_input,
                "success": False,
                "output": None,
                "error": f"Tool '{tool_name}' not found",
            }

        result = await tool(**tool_input)

        execution_time = round(
            time.perf_counter() - start_time,
            3,
        )

        logger.info(
            "TOOL_CALL_SUCCESS | id=%s | tool=%s | duration=%ss",
            tool_call_id,
            tool_name,
            execution_time,
        )

        return {
            "tool_call_id": tool_call_id,
            "tool": tool_name,
            "input": tool_input,
            "success": True,
            "output": result,
            "execution_time": execution_time,
        }

    except Exception as exc:
        execution_time = round(
            time.perf_counter() - start_time,
            3,
        )

        logger.exception(
            "TOOL_CALL_FAILED | id=%s | tool=%s | duration=%ss",
            tool_call_id,
            tool_name,
            execution_time,
        )

        return {
            "tool_call_id": tool_call_id,
            "tool": tool_name,
            "input": tool_input,
            "success": False,
            "output": None,
            "error": str(exc),
            "execution_time": execution_time,
        }


async def tool_executor_node(state: ConversationState):
    steps = state.get("steps", [])
    active_pos_id = state.get("active_position_id")
    ticker = state.get("ticker")

    logger.info(
        "TOOL_EXECUTOR_START | tools=%s",
        [step.tool for step in steps],
    )

    tasks = []
    for step in steps:
        tool_call_id = str(uuid.uuid4())
        tasks.append(execute_tool(step, tool_call_id))

    results = await asyncio.gather(*tasks)

    tool_outputs = []
    sources = []

    seen_urls = {
        source.get("url")
        for source in state.get("sources", [])
        if source.get("url")
    }

    for result in results:
        tool_outputs.append(result)

        if result["success"]:
            output = result["output"]

            # Leverage ActivePosition entity updates when financial tool runs
            if result.get("tool") == "stock_analyzer" and isinstance(output, dict):
                await _update_active_position_from_tool(
                    output,
                    active_position_id=active_pos_id,
                    ticker=ticker or result.get("input", {}).get("ticker"),
                )

            if isinstance(output, list):
                for item in output:
                    url = item.get("url") if isinstance(item, dict) else None
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)
                    sources.append(item)

            elif isinstance(output, dict):
                tool_input = result.get("input", {})
                synthetic_key = f"internal://{result['tool']}/{tool_input.get('ticker') or tool_input.get('query', '')}"

                if synthetic_key in seen_urls:
                    continue

                seen_urls.add(synthetic_key)
                sources.append({
                    "source_type": "structured_data",
                    "tool": result["tool"],
                    "url": synthetic_key,
                    "data": output,
                })

    logger.info(
        "TOOL_EXECUTOR_COMPLETE | executed=%s | successful=%s | new_sources=%s",
        len(results),
        sum(1 for result in results if result["success"]),
        len(sources),
    )

    return {
        "tool_outputs": tool_outputs,
        "sources": sources,
    }
