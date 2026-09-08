"""
New node: runs after router, before planner. Takes the entities the
router extracted (e.g. ["TCS"]) and resolves each to a real
CompanyEntity (correct ticker, exchange, etc.) using the existing
app/services/company_resolver.py — deterministic alias table + provider
validation, not an LLM guess.

Fail-safe by design: if resolution fails for every entity (unknown
company, resolver error), this node returns {} and changes nothing —
the planner falls back to its old behavior of guessing the ticker
itself. This can only make ticker accuracy better or neutral, never worse.
"""

from app.agents.state import ConversationState
from app.services.company_resolver import CompanyResolutionError, resolve_companies
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def company_resolver_node(state: ConversationState):
    entities = state.get("entities", [])

    if not entities:
        return {}

    try:
        resolved = await resolve_companies(entities)
    except CompanyResolutionError as e:
        logger.warning("COMPANY_RESOLUTION_FAILED | entities=%s | error=%s", entities, e)
        return {}

    logger.info(
        "COMPANY_RESOLUTION_OK | entities=%s | resolved=%s",
        entities,
        [(c.name, c.ticker) for c in resolved],
    )

    return {"companies": [c.model_dump() for c in resolved]}
