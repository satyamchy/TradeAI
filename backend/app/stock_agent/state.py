# app/agents/stock_agent/state.py
from typing import TypedDict, Literal, Optional


class ChecklistResult(TypedDict):
    name: str                    # "technical", "fundamental", "risk", "sentiment"
    passed: bool
    score: float                 # 0-10
    reasoning: str
    data_used: dict


class TradeAgentState(TypedDict):
    query: str
    ticker: Optional[str]
    security_id: Optional[str]
    market_data: Optional[dict]

    checklist_results: list[ChecklistResult]
    aggregate_score: Optional[float]

    recommendation: Optional[dict]      # action, trade_type, entry_cap, stop_loss, target
    human_decision: Optional[Literal["approved", "rejected", "modified"]]
    human_feedback: Optional[str]
    modified_recommendation: Optional[dict]

    execution_result: Optional[dict]
    error: Optional[str]