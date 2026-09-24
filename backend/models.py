import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class APIKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_apikey_user_provider"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(50), nullable=False, index=True)
    api_key = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = {"sqlite_autoincrement": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), default="New Chat")
    panel_layout = Column(Text, nullable=True)  # JSON-serialized panel config: [{provider, model, seenModels, visibleSinceTurn}]
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan",
                            order_by="Message.created_at")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    turn_number = Column(Integer, nullable=False)
    role = Column(String(20), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    image = Column(Text, nullable=True)  # base64 data URL attached to a user message
    attached_file_name = Column(String(255), nullable=True)  # display name of an attached text document
    attached_file_content = Column(Text, nullable=True)  # extracted text, truncated to 32k chars
    provider = Column(String(50), nullable=True)  # null for user messages
    model = Column(String(100), nullable=True)    # null for user messages
    # Which frontend panel this assistant answer belongs to (null for user messages
    # and for messages saved before this column existed). Needed because two
    # panels can share the same provider+model — matching on provider/model alone
    # let one panel's history "absorb" another panel's later answers once both
    # had used the same model at some point.
    panel_id = Column(String(64), nullable=True)
    response_time_ms = Column(Float, nullable=True)
    token_count = Column(Integer, nullable=True)
    # % of this model's context window the context actually sent for this call
    # used (chars/4 estimate, same heuristic the compaction trigger uses).
    context_usage_pct = Column(Float, nullable=True)
    # Marks an assistant message's content as structured JSON instead of plain
    # markdown text — e.g. "mom_json" for a meeting-minutes-with-sources reply.
    # Null/default means "render as normal text", so this is fully backward
    # compatible with every existing message.
    content_format = Column(String(20), nullable=True)
    # On a USER message that had "generate with sources" enabled: the ordered
    # sentence table (JSON [{"id": "S1", "text": "..."}, ...]) built from its
    # attached file, shared by every panel's citations for that turn — stored
    # once here rather than duplicated on each assistant response.
    source_sentences = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


class CustomModel(Base):
    __tablename__ = "custom_models"
    __table_args__ = (UniqueConstraint("user_id", "provider", "model", name="uq_custom_model_user_provider_model"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(50), nullable=False, index=True)
    model = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class ContextCompaction(Base):
    __tablename__ = "context_compactions"
    __table_args__ = (UniqueConstraint("conversation_id", "provider", "model", name="uq_compaction_conv_provider_model"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(50), nullable=False)
    model = Column(String(100), nullable=False)
    summary = Column(Text, nullable=False)
    covers_through_turn = Column(Integer, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class Memory(Base):
    """A durable fact extracted from something the user said, auto-injected
    into future prompts (pinned facts always; others when topically relevant)."""
    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    category = Column(String(20), nullable=False)  # identity | preference | fact | contact | project | goal
    pinned = Column(Boolean, default=False, nullable=False)
    source = Column(String(20), default="auto", nullable=False)  # "auto" (extracted) | "manual"
    uses = Column(Integer, default=0, nullable=False)  # times actually injected into a prompt
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class MemoryAuditState(Base):
    """Per-user bookkeeping for the periodic memory audit: how many new
    memories have accumulated since the last audit, and a fingerprint of the
    last-audited set so an unchanged set never re-triggers the LLM call."""
    __tablename__ = "memory_audit_state"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    fingerprint = Column(String(64), nullable=True)
    memories_since_audit = Column(Integer, default=0, nullable=False)
    audited_at = Column(DateTime, nullable=True)


class PanelPreset(Base):
    __tablename__ = "panel_presets"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_preset_user_name"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    config = Column(Text, nullable=False)  # JSON: [{provider, model}, ...]
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# ── Document OCR (scanned form extraction) ──────────────────────────────────
# See scanned_form_extraction.md for the pipeline this implements. Phase 1:
# a vision-language model (no separate OCR engine) reads each whole page and
# returns the doc's field schema directly; per-checkbox crops, a dedicated
# checkbox geometry/state detector, and multi-variant preprocessing comparison
# are later phases (see document-ocr-implementation-plan.md).

class OcrDocument(Base):
    __tablename__ = "ocr_documents"
    # Without this, SQLite reuses a deleted row's id for the next insert once
    # the table is empty — which let a new document collide with an orphaned
    # ocr_pages row still pointing at that reused id (see the 2026-09-23
    # UNIQUE-constraint incident). Same reasoning as Conversation's id.
    __table_args__ = {"sqlite_autoincrement": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    provider = Column(String(50), nullable=False)  # which model read this document, e.g. "local"
    model = Column(String(200), nullable=False)
    page_count = Column(Integer, default=0, nullable=False)
    # queued | processing | done | failed
    status = Column(String(20), default="queued", nullable=False)
    error = Column(Text, nullable=True)
    # Wall-clock time for the whole document, start to finish — with pages
    # read concurrently (see MAX_CONCURRENT_PAGES), this is NOT the sum of the
    # pages' own processing_seconds, it's how long the upload actually took.
    processing_seconds = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    pages = relationship("OcrPage", back_populates="document", cascade="all, delete-orphan",
                          order_by="OcrPage.page_number")


class OcrPage(Base):
    __tablename__ = "ocr_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_number", name="uq_ocrpage_doc_number"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("ocr_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    image_path = Column(Text, nullable=False)  # rendered PNG on disk, relative to data/
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    # queued | processing | done | failed
    status = Column(String(20), default="queued", nullable=False)
    error = Column(Text, nullable=True)
    # How long THIS page's own model call(s) took — since pages run
    # concurrently, this is the number worth comparing across pages/models,
    # not the document's total (which reflects the whole batch, not one page).
    processing_seconds = Column(Float, nullable=True)

    document = relationship("OcrDocument", back_populates="pages")
    fields = relationship("OcrField", back_populates="page", cascade="all, delete-orphan")


class OcrField(Base):
    """One extracted field — matches scanned_form_extraction.md's suggested
    JSON output. bbox_page is null in Phase 1 (a whole-page VLM call has no
    real geometry to report); Phase 2's crop-based pipeline fills it in."""
    __tablename__ = "ocr_fields"

    id = Column(Integer, primary_key=True, autoincrement=True)
    page_id = Column(Integer, ForeignKey("ocr_pages.id", ondelete="CASCADE"), nullable=False, index=True)
    field_id = Column(String(100), nullable=False)  # the model's own field identifier within the page
    question = Column(Text, nullable=True)
    row_label = Column(Text, nullable=True)
    column_label = Column(Text, nullable=True)
    option_label = Column(Text, nullable=True)
    text_value = Column(Text, nullable=True)
    checkbox_state = Column(String(20), nullable=True)  # checked | unchecked | ambiguous | null
    confidence = Column(Float, nullable=True)  # the model's own self-reported confidence, 0-1 — see note in schema.py
    bbox_page = Column(Text, nullable=True)  # JSON [x0,y0,x1,y1] in page pixel space, or null
    crop_id = Column(String(100), nullable=True)
    needs_review = Column(Boolean, default=False, nullable=False)
    reviewed = Column(Boolean, default=False, nullable=False)  # a human has confirmed/corrected this field
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    page = relationship("OcrPage", back_populates="fields")
