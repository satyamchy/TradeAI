import datetime
from sqlalchemy.future import select
from langchain_core.prompts import ChatPromptTemplate

from app.schemas.planner import PlannerResponse, ToolStep
from app.prompts.planner_prompt import PLANNER_PROMPT
from app.llm.groq import get_llm
from app.agents.state import ConversationState
from app.utils.logger import get_logger
from app.db.base import AsyncSessionLocal
from app.db.models import ActivePosition

logger = get_logger(__name__)

llm = get_llm()
planner_llm = llm.bind(response_format={"type": "json_object"})

planner_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", PLANNER_PROMPT),
        (
            "human",
            """
Question:
{query}

Resolved Companies (use these exact tickers if the question is about one of them — do not guess a different ticker):
{companies}

Previous Tool Outputs:
{tool_outputs}
"""
        ),
    ]
)


def _already_searched(query: str, tool_outputs: list) -> bool:
    normalized = query.strip().lower()
    for output in tool_outputs:
        prior_input = output.get("input", {})
        prior_query = str(prior_input.get("query", "")).strip().lower()
        if prior_query and prior_query == normalized:
            return True
    return False


async def planner_node(state: ConversationState):
    loop_count = state.get("loop_count", 0) + 1
    is_bg = state.get("is_background_run", False)
    active_pos_id = state.get("active_position_id")
    ticker = state.get("ticker")

    # Handle background watchdog run or active position evaluation
    if is_bg or active_pos_id:
        # If tool_outputs already present, we have completed analysis
        tool_outputs = state.get("tool_outputs", [])
        if tool_outputs:
            logger.info("PLANNER_BG_COMPLETE | pos_id=%s | ticker=%s", active_pos_id, ticker)
            return {
                "steps": [],
                "is_finished": True,
                "loop_count": loop_count,
            }

        # Retrieve position details if pos_id provided
        target_ticker = ticker
        if active_pos_id and not target_ticker:
            async with AsyncSessionLocal() as session:
                pos = await session.get(ActivePosition, active_pos_id)
                if pos:
                    target_ticker = pos.ticker

        if target_ticker:
            logger.info(
                "PLANNER_ACTIVE_POSITION_EVALUATION | pos_id=%s | ticker=%s",
                active_pos_id,
                target_ticker,
            )
            step = ToolStep(tool="stock_analyzer", input={"ticker": target_ticker})
            return {
                "steps": [step],
                "is_finished": False,
                "loop_count": loop_count,
                "ticker": target_ticker,
            }

    # Standard conversational planning logic
    chain = planner_prompt | planner_llm
    companies = state.get("companies", [])
    companies_text = (
        "\n".join(f"- {c['name']} -> ticker: {c['ticker']}" for c in companies)
        if companies
        else "None resolved."
    )

    response = await chain.ainvoke(
        {
            "query": state.get("query", ""),
            "companies": companies_text,
            "tool_outputs": state.get("tool_outputs", []),
        }
    )

    logger.info("RAW_PLANNER_RESPONSE | %s", response.content)

    planner_response = PlannerResponse.model_validate_json(response.content)

    reason_lower = planner_response.reason.lower()
    if not planner_response.is_finished and (
        "already known" in reason_lower
        or "already have" in reason_lower
        or "already answered" in reason_lower
    ):
        planner_response.is_finished = True
        planner_response.steps = []

    deduped_steps = [
        step
        for step in planner_response.steps
        if not (
            step.tool == "web_search"
            and _already_searched(
                step.input.get("query", ""),
                state.get("tool_outputs", []),
            )
        )
    ]

    if not deduped_steps and planner_response.steps:
        planner_response.is_finished = True

    logger.info(
        "PLANNER_DECISION | query=%s | tools=%s | finished=%s | reason=%s",
        state.get("query", ""),
        [step.tool for step in deduped_steps],
        planner_response.is_finished,
        planner_response.reason,
    )

    return {
        "steps": deduped_steps,
        "is_finished": planner_response.is_finished,
        "loop_count": loop_count,
    }
