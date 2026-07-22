from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserSignup(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def email_must_look_valid(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1] or len(v) < 5:
            raise ValueError("Enter a valid email address")
        return v

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserResponse


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
    panel_layout: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PanelLayoutUpdate(BaseModel):
    panels: list[dict]


# ── Messages ──────────────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    turn_number: int
    role: str
    content: str
    image: Optional[str] = None
    attached_file_name: Optional[str] = None
    attached_file_content: Optional[str] = None
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
    attached_file_name: Optional[str] = None
    attached_file_content: Optional[str] = None  # extracted text, any model can read this


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


class RetryRequest(BaseModel):
    conversation_id: int
    turn_number: int
    provider: str
    model: str


class EditMessageRequest(BaseModel):
    conversation_id: int
    message_id: int
    content: str
    targets: list[ChatTarget]
    image: Optional[str] = None
    attached_file_name: Optional[str] = None
    attached_file_content: Optional[str] = None


# ── Panel Presets ───────────────────────────────────────────────────────────────

class PanelPresetCreate(BaseModel):
    name: str
    panels: list[dict]


class PanelPresetResponse(BaseModel):
    id: int
    name: str
    config: str
    created_at: datetime

    class Config:
        from_attributes = True
