from app.agents.state import ConversationState
import uuid
from app.agents.graph import build_graph
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ConversationAgent:

    def __init__(self):

        self.graph = build_graph()

    async def run(
        self,
        query: str,
    ):
        request_id = str(uuid.uuid4())

        logger.info(
            "AGENT_START | request_id=%s | query=%s",
            request_id,
            query,
        )

        initial_state: ConversationState = {

            "messages": [],
            "query": query,
            "steps": [],
            "tool_outputs": [],
            "sources": [],
            "context": "",
            "answer": "",
            "is_finished": False,
            "error": "",
            "loop_count": 0,

        }

        try:

            result = await self.graph.ainvoke(
                initial_state
            )

            logger.info(
                "AGENT_COMPLETE | request_id=%s | success=%s",
                request_id,
                not bool(result.get("error")),
            )

            return result

        except Exception:

            logger.exception(
                "AGENT_FAILED | request_id=%s",
                request_id,
            )

            raise
        # return await self.graph.ainvoke(
        #     initial_state
        # )