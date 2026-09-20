# import datetime
# from sqlalchemy.future import select

# from app.db.base import AsyncSessionLocal
# from app.db.models import ActivePosition
# from app.agents.graph import trading_compiled_graph
# from app.utils.logger import get_agent_logger, get_logger

# logger = get_logger(__name__)
# log = get_agent_logger("WatchdogService")


# async def evaluate_active_positions():
#     """
#     Processes periodic evaluations on active rows in active_positions table,
#     binding execution to the global compiled graph pipeline.
#     """
#     await log("Initiating periodic active positions watchdog cycle.")

#     try:
#         async with AsyncSessionLocal() as session:
#             stmt = select(ActivePosition).where(ActivePosition.status == "OPEN")
#             result = await session.execute(stmt)
#             open_positions = result.scalars().all()

#         if not open_positions:
#             await log("No open active positions found to evaluate.")
#             return {"evaluated_count": 0, "positions": []}

#         await log(f"Found {len(open_positions)} open positions to evaluate.")

#         results = []
#         for pos in open_positions:
#             await log(
#                 f"Invoking graph pipeline for active position ID={pos.id}, ticker={pos.ticker}",
#                 ticker=pos.ticker,
#             )

#             # Bind execution to global compiled graph pipeline
#             initial_state = {
#                 "messages": [],
#                 "query": f"Evaluate open active position for {pos.ticker}",
#                 "steps": [],
#                 "tool_outputs": [],
#                 "sources": [],
#                 "context": "",
#                 "answer": "",
#                 "is_finished": False,
#                 "error": "",
#                 "loop_count": 0,
#                 "intent": "COMPANY_ANALYSIS",
#                 "entities": [pos.ticker],
#                 "companies": [{"name": pos.symbol or pos.ticker, "ticker": pos.ticker}],
#                 "is_background_run": True,
#                 "active_position_id": pos.id,
#                 "ticker": pos.ticker,
#                 "position_data": {
#                     "id": pos.id,
#                     "ticker": pos.ticker,
#                     "target_price": pos.target_price,
#                     "stop_loss": pos.stop_loss,
#                     "current_price": pos.current_price,
#                 },
#             }

#             try:
#                 graph_output = await trading_compiled_graph.ainvoke(initial_state)

#                 await log(f"Successfully evaluated active position ID={pos.id}.", ticker=pos.ticker, status="SUCCESS")

#                 results.append({
#                     "id": pos.id,
#                     "ticker": pos.ticker,
#                     "status": "EVALUATED",
#                     "error": graph_output.get("error", ""),
#                 })
#             except Exception as eval_err:
#                 await log(f"Failed evaluating active position ID={pos.id}: {eval_err}", ticker=pos.ticker, status="ERROR")
#                 results.append({
#                     "id": pos.id,
#                     "ticker": pos.ticker,
#                     "status": "FAILED",
#                     "error": str(eval_err),
#                 })

#         return {
#             "evaluated_count": len(results),
#             "positions": results,
#             "timestamp": datetime.datetime.utcnow().isoformat(),
#         }

#     except Exception as exc:
#         await log(f"Watchdog evaluation loop encountered exception: {exc}", status="ERROR")
#         return {"evaluated_count": 0, "error": str(exc)}
