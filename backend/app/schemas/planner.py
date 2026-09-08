from typing import Literal, Any
from pydantic import BaseModel, Field, field_validator
from app.tools.registry import TOOLS

class ToolStep(BaseModel):
    tool: str
    input: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tool")
    @classmethod
    def tool_must_exist(cls, v):
        if v not in TOOLS:
            raise ValueError(f"Unknown tool '{v}'. Available: {list(TOOLS.keys())}")
        return v


# class ToolStep(BaseModel):
#     tool: Literal[
#         "web_search",
#         "calculator"
#     ]

#     input: dict[str, Any] = Field(
#         description=(
#             "Arguments for the selected tool. "
#             "For web_search, use {'query': '<search query>'}. "
#             "For calculator, use {'expression': '<mathematical expression>'}. "
#             "Never return an empty object."
#         )
#     )

class PlannerResponse(BaseModel):
    steps: list[ToolStep] = Field(default_factory=list)
    is_finished: bool
    reason: str = ""