from app.agents.state import ConversationState


async def formatter_node(
    state: ConversationState,
):

    answer = (state.get("answer") or "").strip()

    if not answer:
        answer = "Sorry, I couldn't generate an answer."

    structured_data = None
    sources = state.get("sources", [])

    for s in sources:
        if isinstance(s, dict) and s.get("source_type") == "structured_data" and "data" in s:
            structured_data = s["data"]
            break

    return {
        "answer": answer,
        "sources": sources,
        "structured_data": structured_data,
        "error": state.get("error", "")
    }