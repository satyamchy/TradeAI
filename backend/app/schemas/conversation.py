from pydantic import BaseModel, Field
from typing import List


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