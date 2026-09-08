import operator
from typing import Annotated, Any, Optional
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from app.schemas.planner import ToolStep

class ConversationState(TypedDict):

    # Conversation history
    messages: Annotated[list[BaseMessage], add_messages]
    # Original query
    query: str
    # Planner output
    steps: list[ToolStep]
    # Outputs returned from tools (accumulates across loop iterations)
    tool_outputs: Annotated[list[Any], operator.add]
    # Unified sources from all tools (accumulates across loop iterations)
    sources: Annotated[list[dict], operator.add]
    # Context built from sources
    context: str
    # Final answer
    answer: str
    # Planner decision
    is_finished: bool
    # Error
    error: str
    # Number of planner<->tool_executor round trips so far
    loop_count: int
    # --- Added in Phase 2 (router) ---
    intent: str
    entities: list[str]
    # --- Added in Phase 3 (company resolver) ---
    companies: list[dict]
    # --- Asynchronous, Database-backed LangGraph extensions ---
    is_background_run: bool
    active_position_id: Optional[int]
    ticker: Optional[str]
    position_data: Optional[dict]

# Type alias for trading state
TradingGraphState = ConversationState
