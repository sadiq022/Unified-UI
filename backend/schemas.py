from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# ── API Keys ──────────────────────────────────────────────────────────────────

class APIKeyCreate(BaseModel):
    provider: str
    api_key: str


class APIKeyResponse(BaseModel):
    id: int
    provider: str
    key_preview: str  # masked key like "sk-...abc"
    created_at: datetime

    class Config:
        from_attributes = True


# ── Custom Models ─────────────────────────────────────────────────────────────

class CustomModelCreate(BaseModel):
    provider: str
    model: str


class CustomModelResponse(BaseModel):
    id: int
    provider: str
    model: str
    created_at: datetime

    class Config:
        from_attributes = True


# ── Conversations ─────────────────────────────────────────────────────────────

class ConversationCreate(BaseModel):
    title: Optional[str] = "New Chat"


class ConversationUpdate(BaseModel):
    title: str


class ConversationResponse(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Messages ──────────────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    turn_number: int
    role: str
    content: str
    image: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    response_time_ms: Optional[float] = None
    token_count: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatTarget(BaseModel):
    provider: str
    model: str


class ChatRequest(BaseModel):
    conversation_id: int
    message: str
    targets: list[ChatTarget]  # which models to send to
    image: Optional[str] = None  # base64 data URL, only usable by vision-capable models


class ChatResponseItem(BaseModel):
    provider: str
    model: str
    content: str
    response_time_ms: float
    token_count: Optional[int] = None
    error: Optional[str] = None


class ChatResponse(BaseModel):
    turn_number: int
    user_message: MessageResponse
    responses: list[ChatResponseItem]
