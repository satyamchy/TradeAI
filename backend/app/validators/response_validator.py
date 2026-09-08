from app.schemas.conversation import RunResponse, Source


def validate_response(answer: str, sources: list[dict], query: str) -> RunResponse:
    clean_answer = (answer or "").strip()

    clean_sources = []
    for s in sources:
        clean_sources.append(
            Source(
                title=s.get("title", "Untitled source"),
                url=s.get("url", ""),
                snippet=s.get("snippet", ""),
            )
        )

    if not clean_answer:
        return RunResponse(
            query=query,
            answer="I could not generate a valid answer from the search results.",
            sources=clean_sources,
            success=False,
            message="empty_answer",
        )

    return RunResponse(
        query=query,
        answer=clean_answer,
        sources=clean_sources,
        success=True,
        message="ok",
    )