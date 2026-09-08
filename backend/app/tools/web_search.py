import logging
from langchain_community.tools import DuckDuckGoSearchResults

logger = logging.getLogger(__name__)

MANIFEST = {
    "name": "web_search",
    "description": "Search the internet for current or external information.",
    "input_schema": {"query": "search query string"},
}

async def web_search( query: str,max_results: int = 3,) -> list[dict]:

    tool = DuckDuckGoSearchResults(
        output_format="list",
        num_results=max_results,
    )

    try:

        results = await tool.ainvoke(query)

    except Exception as e:

        logger.exception(
            "WEB_SEARCH_FAILED | query=%s",
            query,
        )
 
        # Re-raise so tool_executor_node records this as
        # success=False with a real error, instead of silently
        # returning an empty list that looks like "zero results".
        raise RuntimeError(
            f"web_search failed for query='{query}': {e}"
        ) from e

    if not results:

        logger.warning(
            "WEB_SEARCH_EMPTY | query=%s",
            query,
        )

        return []

    normalized = []

    for item in results[:max_results]:

        normalized.append(

            {
                "title": item.get("title")
                or item.get("source")
                or "Untitled",

                "url": item.get("link")
                or item.get("url")
                or "",

                "snippet": item.get("snippet")
                or item.get("body")
                or "",
            }

        )

    return normalized