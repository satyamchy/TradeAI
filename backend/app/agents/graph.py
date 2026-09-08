from langgraph.graph import START, END, StateGraph

from app.agents.state import ConversationState, TradingGraphState
from app.agents.planner import planner_node
from app.agents.router import router_node
from app.agents.company_resolver_node import company_resolver_node
from app.agents.tool_executor import tool_executor_node
from app.agents.answer import answer_node
from app.agents.formatter import formatter_node

MAX_LOOPS = 4  # hard safety cap: planner<->tool_executor round trips


def initial_routing(state: ConversationState):
    """Route background runs directly to planner bypassing conversational nodes."""
    if state.get("is_background_run", False):
        return "planner"
    return "router"


def planner_router(state: ConversationState):
    is_bg = state.get("is_background_run", False)

    # If background run is finished or reached loop cap, route directly to formatter / END
    if is_bg and (state.get("is_finished", False) or state.get("loop_count", 0) >= MAX_LOOPS or not state.get("steps")):
        return "formatter"

    # Safety net: prevent runaway loops
    if state.get("loop_count", 0) >= MAX_LOOPS:
        return "answer_generator"

    # If the LLM/planner says it is done
    if state.get("is_finished", False):
        return "answer_generator"

    # If no tool execution steps requested
    if not state.get("steps"):
        return "answer_generator"

    return "tool_executor"


def build_graph():
    builder = StateGraph(ConversationState)

    builder.add_node("router", router_node)
    builder.add_node("company_resolver", company_resolver_node)
    builder.add_node("planner", planner_node)
    builder.add_node("tool_executor", tool_executor_node)
    builder.add_node("answer_generator", answer_node)
    builder.add_node("formatter", formatter_node)

    # Entrypoint conditional edge routing
    builder.add_conditional_edges(
        START,
        initial_routing,
        {
            "planner": "planner",
            "router": "router",
        },
    )

    builder.add_edge("router", "company_resolver")
    builder.add_edge("company_resolver", "planner")

    builder.add_conditional_edges(
        "planner",
        planner_router,
        {
            "tool_executor": "tool_executor",
            "answer_generator": "answer_generator",
            "formatter": "formatter",
        },
    )

    builder.add_edge("tool_executor", "planner")
    builder.add_edge("answer_generator", "formatter")
    builder.add_edge("formatter", END)

    return builder.compile()


# Global compiled graph pipeline instances
trading_graph = build_graph()
trading_compiled_graph = trading_graph
