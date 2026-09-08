"""
New node: classifies intent before the existing planner runs.

For GENERAL / WEB_RESEARCH, everything downstream is 100% unchanged —
this node only annotates state with intent/entities and passes through
to your existing planner -> tool_executor -> answer -> formatter flow.

Finance intents (COMPANY_ANALYSIS, COMPANY_COMPARISON, etc.) also pass
through to the same existing flow for now — they're just tagged. A
dedicated finance sub-graph consuming these tags is a later phase, so
nothing breaks or forks yet; this node is purely additive.
"""

from langchain_core.prompts import ChatPromptTemplate

from app.agents.state import ConversationState
from app.llm.groq import get_llm
from app.prompts.router_prompt import ROUTER_PROMPT
from app.schemas.router import RouteDecision
from app.utils.logger import get_logger

logger = get_logger(__name__)

llm = get_llm()

router_llm = llm.bind(response_format={"type": "json_object"})

router_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", ROUTER_PROMPT),
    ]
)


async def router_node(state: ConversationState):
    chain = router_prompt | router_llm

    response = await chain.ainvoke({"query": state["query"]})

    logger.info("RAW_ROUTER_RESPONSE | %s", response.content)

    try:
        decision = RouteDecision.model_validate_json(response.content)
    except Exception as e:
        # Fail safe: if routing breaks for any reason, fall back to
        # GENERAL rather than blocking the existing working flow.
        logger.warning("ROUTER_PARSE_FAILED | error=%s | falling back to GENERAL", e)
        decision = RouteDecision(intent="GENERAL", confidence=0.0, entities=[], reasoning="router parse failed")

    logger.info(
        "ROUTE_DECISION | query=%s | intent=%s | confidence=%.2f | entities=%s",
        state["query"], decision.intent, decision.confidence, decision.entities,
    )

    return {
        "intent": decision.intent,
        "entities": decision.entities,
    }
