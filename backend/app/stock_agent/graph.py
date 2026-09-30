# app/agents/stock_agent/graph.py
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver  # swap for Postgres/Redis checkpointer in prod
from langgraph.types import interrupt, Command

from backend.app.stock_agent.state import TradeAgentState
from backend.app.stock_agent.nodes import (
    resolve_ticker_node, technical_checklist_node, fundamental_checklist_node,
    risk_checklist_node, sentiment_checklist_node, aggregate_checklist_node,
    generate_recommendation_node, execute_order_node,
)


async def fetch_market_data_node(state: TradeAgentState) -> dict:
    # market_data already fetched during resolution — this node exists so the
    # parallel checklist nodes have a clean, single upstream dependency
    return {}


async def human_approval_node(state: TradeAgentState) -> dict:
    decision = interrupt({
        "recommendation": state["recommendation"],
        "checklist_results": state["checklist_results"],
        "message": "Review this recommendation and approve, reject, or modify before execution.",
    })
    # `decision` is whatever the API layer passes back via Command(resume=...)
    return {
        "human_decision": decision.get("decision"),
        "modified_recommendation": decision.get("modified_recommendation"),
        "human_feedback": decision.get("feedback"),
    }


def route_after_approval(state: TradeAgentState) -> str:
    if state["human_decision"] in ("approved", "modified"):
        return "execute_order"
    return "__end__"


def build_graph():
    graph = StateGraph(TradeAgentState)

    graph.add_node("resolve_ticker", resolve_ticker_node)
    graph.add_node("fetch_market_data", fetch_market_data_node)
    graph.add_node("technical_checklist", technical_checklist_node)
    graph.add_node("fundamental_checklist", fundamental_checklist_node)
    graph.add_node("risk_checklist", risk_checklist_node)
    graph.add_node("sentiment_checklist", sentiment_checklist_node)
    graph.add_node("aggregate_checklist", aggregate_checklist_node)
    graph.add_node("generate_recommendation", generate_recommendation_node)
    graph.add_node("human_approval", human_approval_node)
    graph.add_node("execute_order", execute_order_node)

    graph.set_entry_point("resolve_ticker")
    graph.add_edge("resolve_ticker", "fetch_market_data")

    # fan out to checklist nodes in parallel
    for node in ["technical_checklist", "fundamental_checklist", "risk_checklist", "sentiment_checklist"]:
        graph.add_edge("fetch_market_data", node)
        graph.add_edge(node, "aggregate_checklist")

    graph.add_edge("aggregate_checklist", "generate_recommendation")
    graph.add_edge("generate_recommendation", "human_approval")
    graph.add_conditional_edges("human_approval", route_after_approval, {
        "execute_order": "execute_order", "__end__": END,
    })
    graph.add_edge("execute_order", END)

    checkpointer = MemorySaver()  # persists state across the interrupt — MUST be durable in prod
    return graph.compile(checkpointer=checkpointer)


stock_agent = build_graph()