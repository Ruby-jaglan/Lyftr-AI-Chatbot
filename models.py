from typing import Optional, Literal, List
from pydantic import BaseModel, Field, field_validator

class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    message: str = Field(..., min_length=1)
    system_prompt: Optional[str] = None
    @field_validator("session_id")
    @classmethod
    def valid_session(cls, value):
        value = value.strip()
        if not value: raise ValueError("session_id cannot be blank")
        if len(value) > 128: raise ValueError("session_id must be at most 128 characters")
        return value
    @field_validator("message")
    @classmethod
    def valid_message(cls, value):
        value = value.strip()
        if not value: raise ValueError("message cannot be blank")
        if len(value) > 4000: raise ValueError("message must be at most 4000 characters")
        return value

class ResponseMetadata(BaseModel):
    resolution_source: Literal["LIVE_INFERENCE", "LLM_CACHE"]
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    key_id: Optional[str] = None
    fallback_attempts: int = 0

class ChatResponse(BaseModel):
    session_id: str
    reply: str
    metadata: ResponseMetadata

class MessageResponse(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    metadata: Optional[dict] = None

class SessionHistoryResponse(BaseModel):
    session_id: str
    messages: List[MessageResponse]

class HealthResponse(BaseModel):
    status: str
    keys_configured: int
    cache_enabled: bool
