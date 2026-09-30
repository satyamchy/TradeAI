# app/api/routes/agent.py
from fastapi import APIRouter, HTTPException
from langgraph.types import Command
from backend.app.stock_agent.graph import stock_agent

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/analyze")
async def start_run(query: str):
    run_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": run_id}}
    result = await stock_agent.ainvoke({"query": query, "checklist_results": []}, config=config)

    # if interrupted, result contains the interrupt payload instead of a final state
    return {"run_id": run_id, "status": "awaiting_approval" if "__interrupt__" in result else "completed", "state": result}


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    config = {"configurable": {"thread_id": run_id}}
    snapshot = await stock_agent.aget_state(config)
    if not snapshot:
        raise HTTPException(404, "Run not found")
    return {"state": snapshot.values, "next": snapshot.next}


@router.post("/runs/{run_id}/decision")
async def submit_decision(run_id: str, decision: str, modified_recommendation: dict | None = None, feedback: str | None = None):
    config = {"configurable": {"thread_id": run_id}}
    result = await stock_agent.ainvoke(
        Command(resume={"decision": decision, "modified_recommendation": modified_recommendation, "feedback": feedback}),
        config=config,
    )
    return {"run_id": run_id, "state": result}