import asyncio
import time
import traceback
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.database import get_db
from backend.models import APIKey, Conversation, Message
from backend.schemas import ChatRequest, ChatResponse, ChatResponseItem, MessageResponse
from backend.providers import get_provider

router = APIRouter(prefix="/api/chat", tags=["Chat"])


async def _call_model(provider_name: str, model: str, api_key: str, messages: list[dict]) -> ChatResponseItem:
    """Call a single model and return the response with timing."""
    start = time.time()
    try:
        provider = get_provider(provider_name)
        result = await provider.chat(messages, model, api_key)
        elapsed_ms = (time.time() - start) * 1000

        return ChatResponseItem(
            provider=provider_name,
            model=model,
            content=result["content"],
            response_time_ms=round(elapsed_ms, 1),
            token_count=result.get("token_count"),
        )
    except Exception as e:
        elapsed_ms = (time.time() - start) * 1000
        error_detail = str(e)
        # Try to extract more useful error info
        if hasattr(e, 'response'):
            try:
                error_detail = e.response.text
            except Exception:
                pass
        return ChatResponseItem(
            provider=provider_name,
            model=model,
            content="",
            response_time_ms=round(elapsed_ms, 1),
            error=error_detail,
        )


@router.post("/send", response_model=ChatResponse)
async def send_message(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    """
    Send a user message to one or more models simultaneously.
    Returns all responses along with the turn number.
    """
    # Verify conversation exists
    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == req.conversation_id)
    )
    conv = conv_result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Determine the next turn number
    max_turn = await db.execute(
        select(func.max(Message.turn_number)).where(
            Message.conversation_id == req.conversation_id
        )
    )
    current_max = max_turn.scalar() or 0
    turn_number = current_max + 1

    # Save the user message
    user_msg = Message(
        conversation_id=req.conversation_id,
        turn_number=turn_number,
        role="user",
        content=req.message,
    )
    db.add(user_msg)
    await db.flush()
    await db.refresh(user_msg)

    # Build conversation history for context
    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == req.conversation_id)
        .order_by(Message.created_at)
    )
    all_messages = history_result.scalars().all()

    # Build messages list (use only user messages and the first assistant response per turn for context)
    seen_turns = {}
    context_messages = []
    for msg in all_messages:
        if msg.role == "user":
            context_messages.append({
                "role": "user",
                "content": msg.content,
                "turn_number": msg.turn_number,
            })
        elif msg.role == "assistant" and msg.turn_number not in seen_turns:
            # Include only one assistant response per turn to avoid confusion
            seen_turns[msg.turn_number] = True
            context_messages.append({
                "role": "assistant",
                "content": msg.content,
                "turn_number": msg.turn_number,
            })

    # Look up API keys for each target
    api_keys = {}
    for target in req.targets:
        if target.provider not in api_keys:
            key_result = await db.execute(
                select(APIKey).where(APIKey.provider == target.provider)
            )
            key_obj = key_result.scalar_one_or_none()
            if not key_obj:
                raise HTTPException(
                    status_code=400,
                    detail=f"No API key configured for provider: {target.provider}"
                )
            api_keys[target.provider] = key_obj.api_key

    # Call all models concurrently
    tasks = [
        _call_model(target.provider, target.model, api_keys[target.provider], context_messages)
        for target in req.targets
    ]
    responses = await asyncio.gather(*tasks)

    # Save assistant responses to database
    for resp in responses:
        if not resp.error:
            assistant_msg = Message(
                conversation_id=req.conversation_id,
                turn_number=turn_number,
                role="assistant",
                content=resp.content,
                provider=resp.provider,
                model=resp.model,
                response_time_ms=resp.response_time_ms,
                token_count=resp.token_count,
            )
            db.add(assistant_msg)

    # Update conversation title from first user message if still "New Chat"
    if conv.title == "New Chat" and turn_number == 1:
        # Use first 60 chars of the message as the title
        conv.title = req.message[:60] + ("..." if len(req.message) > 60 else "")

    await db.flush()

    user_msg_response = MessageResponse(
        id=user_msg.id,
        conversation_id=user_msg.conversation_id,
        turn_number=user_msg.turn_number,
        role=user_msg.role,
        content=user_msg.content,
        created_at=user_msg.created_at,
    )

    return ChatResponse(
        turn_number=turn_number,
        user_message=user_msg_response,
        responses=list(responses),
    )


@router.get("/history/{conversation_id}", response_model=list[MessageResponse])
async def get_history(conversation_id: int, db: AsyncSession = Depends(get_db)):
    """Get full message history for a conversation."""
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    messages = result.scalars().all()
    return messages
