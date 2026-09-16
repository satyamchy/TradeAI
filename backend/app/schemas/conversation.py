from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict

class Source(BaseModel):
    title: str = Field(default="Untitled source")
    url: str = Field(default="")
    snippet: str = Field(default="")


class RunResponse(BaseModel):
    query: str
    answer: str
    sources: List[Source] = []
    structured_data: Optional[Dict[str, Any]] = None
    success: bool = True
    message: str = "ok"


class ChatRequest(BaseModel):
    """
    Inbound conversation query payload.

    - query (str, required): Natural language question (e.g. 'Analyze TCS for intraday trading')
    - ticker (str, optional): Explicit ticker symbol (e.g. 'TCS.NS')
    """
    query: str = Field(..., description="Inbound user query for the AI agent")
    ticker: Optional[str] = Field(None, description="Optional target ticker symbol")


class ChatResponse(BaseModel):
    """
    Structured conversational response.

    - answer: Markdown-formatted multi-horizon analysis and AI reasoning
    - sources: Retrieved citations and data references
    - structured_data: Structured financial indicator payload if a stock tool was invoked
    """
    query: str
    answer: str
    sources: List[Source] = []
    structured_data: Optional[Dict[str, Any]] = None
    success: bool = True
    message: str = "ok"
