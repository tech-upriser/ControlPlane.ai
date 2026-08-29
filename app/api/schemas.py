# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
import time
import uuid

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: Optional[str] = None
    tool_calls: Optional[List[dict]] = None
    tool_call_id: Optional[str] = None

class ToolFunction(BaseModel):
    name: str
    description: Optional[str] = None
    parameters: Optional[dict] = None

class Tool(BaseModel):
    type: Literal["function"] = "function"
    function: ToolFunction

class ChatCompletionRequest(BaseModel):
    model: str = "mock"
    messages: List[ChatMessage]
    stream: bool = True
    temperature: Optional[float] = 1.0
    max_tokens: Optional[int] = None
    tools: Optional[List[Tool]] = None
    tool_choice: Optional[str] = None
    # ControlPlane-specific headers are read from request, not body

class Delta(BaseModel):
    role: Optional[str] = None
    content: Optional[str] = None
    tool_calls: Optional[List[dict]] = None

class Choice(BaseModel):
    index: int = 0
    delta: Delta
    finish_reason: Optional[str] = None

class ChatCompletionChunk(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = "mock"
    choices: List[Choice]
