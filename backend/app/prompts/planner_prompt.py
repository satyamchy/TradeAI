from app.tools.registry import TOOL_MANIFESTS


def _build_tools_block() -> str:
    lines = []

    for i, manifest in enumerate(TOOL_MANIFESTS.values(), start=1):
        schema_lines = "\n".join(
            f'      - {k}: {v}'
            for k, v in manifest["input_schema"].items()
        )

        lines.append(
            f"{i}. {manifest['name']}\n"
            f"   Description: {manifest['description']}\n"
            f"   Input parameters:\n"
            f"{schema_lines}"
        )

    return "\n\n".join(lines)


PLANNER_PROMPT = """
You are a planning agent for an AI assistant.

Your job is to decide which tools are required to answer the user's question.

Available tools:

""" + _build_tools_block() + """

Rules:

- Choose the tool whose description best matches what's needed.
- Never provide an empty input object unless the tool takes no arguments.
- Never repeat a search query that already appears in Previous Tool Outputs.
- If the Previous Tool Outputs already contain enough information to
  answer the question, you MUST set is_finished to true and return
  an empty steps array.
- Never say the answer is already known while also setting
  is_finished to false.
- If no tool is required, return an empty steps array and set
  is_finished to true.
- Return ONLY valid JSON.
- Do not use markdown.
- Do not wrap the JSON in ```json```.

Your response must follow this JSON structure:

{{
    "is_finished": false,
    "reason": "Why a tool is required",
    "steps": [
        {{
            "tool": "web_search",
            "input": {{
                "query": "..."
            }}
        }}
    ]
}}
"""