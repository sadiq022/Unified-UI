from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from backend.database import get_db
from backend.models import Conversation
from backend.schemas import ConversationCreate, ConversationUpdate, ConversationResponse

router = APIRouter(prefix="/api/conversations", tags=["Conversations"])


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(db: AsyncSession = Depends(get_db)):
    """List all conversations, newest first."""
    result = await db.execute(
        select(Conversation).order_by(Conversation.updated_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=ConversationResponse)
async def create_conversation(data: ConversationCreate, db: AsyncSession = Depends(get_db)):
    """Create a new conversation."""
    conv = Conversation(title=data.title)
    db.add(conv)
    await db.flush()
    await db.refresh(conv)
    return conv


@router.put("/{conversation_id}/title", response_model=ConversationResponse)
async def update_title(conversation_id: int, data: ConversationUpdate, db: AsyncSession = Depends(get_db)):
    """Rename a conversation."""
    result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conv.title = data.title
    await db.flush()
    return conv


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a conversation and all its messages."""
    result = await db.execute(delete(Conversation).where(Conversation.id == conversation_id))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"message": "Conversation deleted"}
