from app.agents.conversation_agent import ConversationAgent
from app.schemas.conversation import RunResponse, Source
from app.services.performance_tracker import save_snapshot_from_data

agent = ConversationAgent()

async def run_conversation(query: str) -> RunResponse:
    res = await agent.run(query)
    
    raw_sources = res.get("sources", [])
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
                
    structured_data = res.get("structured_data")
    if structured_data and isinstance(structured_data, dict) and structured_data.get("ticker"):
        try:
            await save_snapshot_from_data(structured_data)
        except Exception:
            pass

    return RunResponse(
        query=query,
        answer=res.get("answer", ""),
        sources=formatted_sources,
        structured_data=structured_data,
        success=not bool(res.get("error")),
        message=res.get("error") or "ok",
    )