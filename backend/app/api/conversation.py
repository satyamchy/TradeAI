"""
Conversation API Router.
Provides conversational multi-horizon decision support for Indian stocks.

Endpoints:
- POST /api/conversation: Primary conversational endpoint. Parses queries, invokes LangGraph, returns analysis.
- GET  /api/conversation: Backwards-compatible GET query handler.
"""

from typing import List, Optional, Any, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agents.graph import trading_compiled_graph
from app.agents.state import TradingGraphState
from app.utils.logger import log_agent_event, get_logger
from app.schemas.conversation import Source, RunResponse

logger = get_logger(__name__)

router = APIRouter(tags=["conversation"])


class ChatRequest(BaseModel):
    """
    Inbound conversation query payload.
    
    Fields:
    - query (str, required): Natural language question or command (e.g. 'Analyze TCS for intraday trading').
    - ticker (str, optional): Optional explicit ticker symbol (e.g. 'TCS.NS', 'RELIANCE.NS').
    """
    query: str = Field(..., description="Inbound user query for the AI agent")
    ticker: Optional[str] = Field(None, description="Optional target ticker symbol")


class ChatResponse(BaseModel):
    """
    Structured conversational response.
    
    Fields:
    - query (str): The original user query.
    - answer (str): Markdown-formatted multi-horizon analysis and AI reasoning.
    - sources (List[Source]): Retrieved citations and data references.
    - structured_data (Optional[Dict[str, Any]]): Structured financial indicator payload if a stock tool was invoked.
    - success (bool): True if execution completed without fatal errors.
    - message (str): Status message ('ok' or error detail).
    """
    query: str
    answer: str
    sources: List[Source] = []
    structured_data: Optional[Dict[str, Any]] = None
    success: bool = True
    message: str = "ok"


@router.post("", response_model=ChatResponse)
@router.post("/", response_model=ChatResponse)
async def process_conversation(req: ChatRequest):
    """
    Processes natural language trading queries through the compiled LangGraph pipeline.

    - **Purpose**: Full-cycle AI financial analysis evaluating live quotes, technical indicators, and news.
    - **Method**: POST
    - **Payload**:
      ```json
      {
        "query": "What is the intraday trend and support/resistance for Reliance?",
        "ticker": "RELIANCE.NS"
      }
      ```
    - **Response**:
      ```json
      {
        "query": "...",
        "answer": "### Multi-Horizon Analysis for RELIANCE.NS\n- **Intraday Bias**: Bullish...",
        "sources": [{"title": "Market Data Tool (stock_analyzer)", "url": "...", "snippet": "..."}],
        "structured_data": {"ticker": "RELIANCE.NS", "current_price": 1294.9, "indicators": {...}},
        "success": true,
        "message": "ok"
      }
      ```
    """
    user_query = req.query.strip()
    if not user_query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    target_ticker = req.ticker.strip().upper() if req.ticker else None

    await log_agent_event(
        agent_name="ConversationRouter",
        message=f"Received inbound user query: '{user_query}'",
        ticker=target_ticker,
        status="INFO",
    )

    initial_state: TradingGraphState = {
        "messages": [],
        "query": user_query,
        "steps": [],
        "tool_outputs": [],
        "sources": [],
        "context": "",
        "answer": "",
        "is_finished": False,
        "error": "",
        "loop_count": 0,
        "intent": "",
        "entities": [target_ticker] if target_ticker else [],
        "companies": [{"name": target_ticker, "ticker": target_ticker}] if target_ticker else [],
        "is_background_run": False,
        "active_position_id": None,
        "ticker": target_ticker,
        "position_data": None,
    }

    try:
        result = await trading_compiled_graph.ainvoke(initial_state)

        # Format sources
        raw_sources = result.get("sources", [])
        formatted_sources = []
        for s in raw_sources:
            if isinstance(s, dict):
                if s.get("source_type") == "structured_data":
                    tool_name = s.get("tool", "stock_analyzer")
                    formatted_sources.append(
                        Source(
                            title=f"Market Data Tool ({tool_name})",
                            url=s.get("url", ""),
                            snippet=f"Retrieved live financial metrics via {tool_name}",
                        )
                    )
                else:
                    formatted_sources.append(
                        Source(
                            title=s.get("title", s.get("url", "Source")),
                            url=s.get("url", ""),
                            snippet=s.get("snippet", ""),
                        )
                    )

        has_error = bool(result.get("error"))
        status_str = "ERROR" if has_error else "SUCCESS"
        log_msg = f"Completed run for query '{user_query}'. Result: {result.get('error') or 'OK'}"

        await log_agent_event(
            agent_name="ConversationRouter",
            message=log_msg,
            ticker=target_ticker,
            status=status_str,
        )

        return ChatResponse(
            query=user_query,
            answer=result.get("answer", ""),
            sources=formatted_sources,
            structured_data=result.get("structured_data"),
            success=not has_error,
            message=result.get("error") or "ok",
        )

    except Exception as exc:
        await log_agent_event(
            agent_name="ConversationRouter",
            message=f"Failed processing query '{user_query}': {str(exc)}",
            ticker=target_ticker,
            status="ERROR",
        )
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("", response_model=ChatResponse)
@router.get("/", response_model=ChatResponse)
async def get_conversation(query: str):
    """
    Backwards-compatible GET query handler.
    - **Method**: GET
    - **Query Param**: `query` (string)
    - **Response**: `ChatResponse` model.
    """
    return await process_conversation(ChatRequest(query=query))
