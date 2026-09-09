from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from backend.database import get_db
from backend.models import Memory, User
from backend.schemas import MemoryResponse, MemoryPinUpdate
from backend.auth import get_current_user

router = APIRouter(prefix="/api/memories", tags=["Memories"])


@router.get("", response_model=list[MemoryResponse])
async def list_memories(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """List everything remembered about the current user — pinned facts first, then newest first."""
    result = await db.execute(
        select(Memory)
        .where(Memory.user_id == current_user.id)
        .order_by(Memory.pinned.desc(), Memory.created_at.desc())
    )
    return result.scalars().all()


@router.patch("/{memory_id}", response_model=MemoryResponse)
async def update_memory_pin(
    memory_id: int,
    data: MemoryPinUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually pin or unpin a memory (pinned facts are injected into every turn)."""
    result = await db.execute(
        select(Memory).where(Memory.id == memory_id, Memory.user_id == current_user.id)
    )
    memory = result.scalar_one_or_none()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    memory.pinned = data.pinned
    await db.flush()
    await db.refresh(memory)
    return memory


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Forget a stored fact."""
    result = await db.execute(
        delete(Memory).where(Memory.id == memory_id, Memory.user_id == current_user.id)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"message": "Memory deleted"}
