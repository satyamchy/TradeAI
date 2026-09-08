"""
calculator tool
Safe arithmetic evaluation — never uses raw eval().

pip install numexpr --break-system-packages
"""

import numexpr



MANIFEST = {
    "name": "calculator",
    "description": "Solve mathematical expressions.",
    "input_schema": {"expression": "mathematical expression"},
}

# async def run(expression: str) -> str:
#     return str(eval(expression, {"__builtins__": {}}))  # use a safe eval lib in production


async def calculator(expression: str) -> dict:
    """
    Args:
        expression: math expression as a string, e.g. "23 * (4 + 1) / 2"
    """
    try:
        # numexpr only evaluates numeric expressions — no code execution risk
        result = numexpr.evaluate(expression).item()
        return {
            "tool": "calculator",
            "output": result,
            "source": "local computation",
        }
    except Exception as e:
        return {
            "tool": "calculator",
            "output": None,
            "error": f"Could not evaluate expression: {e}",
            "source": "local computation",
        }
