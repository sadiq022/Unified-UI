from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from backend.database import get_db
from backend.models import CustomModel, User
from backend.schemas import CustomModelCreate, CustomModelResponse
from backend.auth import get_current_user

router = APIRouter(prefix="/api/custom-models", tags=["Custom Models"])


@router.get("", response_model=list[CustomModelResponse])
async def list_custom_models(
    provider: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List the current user's saved custom models, optionally filtered by provider."""
    query = select(CustomModel).where(CustomModel.user_id == current_user.id).order_by(CustomModel.created_at)
    if provider:
        query = query.where(CustomModel.provider == provider)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("", response_model=CustomModelResponse)
async def add_custom_model(
    data: CustomModelCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save a custom model name for a provider (idempotent per user)."""
    existing = await db.execute(
        select(CustomModel).where(
            CustomModel.user_id == current_user.id,
            CustomModel.provider == data.provider,
            CustomModel.model == data.model,
        )
    )
    found = existing.scalar_one_or_none()
    if found:
        return found

    new_model = CustomModel(provider=data.provider, model=data.model, user_id=current_user.id)
    db.add(new_model)
    await db.flush()
    await db.refresh(new_model)
    return new_model


@router.delete("/{model_id}")
async def delete_custom_model(
    model_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a saved custom model."""
    result = await db.execute(
        delete(CustomModel).where(CustomModel.id == model_id, CustomModel.user_id == current_user.id)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Custom model not found")
    return {"message": "Custom model deleted"}
