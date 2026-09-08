from typing import List


def build_context(
    sources: list[dict]
):

    if not sources:
        return "No sources available."

    docs = []

    for idx, source in enumerate(
        sources,
        start=1,
    ):

        if source.get("source_type") == "structured_data":
            data = source.get("data", {})
            docs.append(
                f"""
Source {idx} (structured financial data via {source.get("tool")})

{data}
"""
            )
            continue

        docs.append(
            f"""
Source {idx}

Title:
{source.get("title")}

URL:
{source.get("url")}

Snippet:
{source.get("snippet")}
"""
        )

    return "\n".join(docs)