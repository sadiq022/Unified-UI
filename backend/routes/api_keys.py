from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from backend.database import get_db
from backend.models import APIKey, CustomModel, User
from backend.schemas import APIKeyCreate, APIKeyResponse
from backend.providers import get_models, get_vision_models
from backend.auth import get_current_user

router = APIRouter(prefix="/api/keys", tags=["API Keys"])


def mask_key(key: str) -> str:
    """Mask an API key for display, showing only first 4 and last 4 chars."""
    if len(key) <= 10:
        return key[:2] + "..." + key[-2:]
    return key[:4] + "..." + key[-4:]


@router.get("", response_model=list[APIKeyResponse])
async def list_api_keys(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """List the current user's saved API keys (masked)."""
    result = await db.execute(
        select(APIKey).where(APIKey.user_id == current_user.id).order_by(APIKey.provider)
    )
    keys = result.scalars().all()
    return [
        APIKeyResponse(
            id=k.id,
            provider=k.provider,
            key_preview=mask_key(k.api_key),
            created_at=k.created_at,
        )
        for k in keys
    ]


@router.post("", response_model=APIKeyResponse)
async def save_api_key(
    data: APIKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save or update the current user's API key for a provider."""
    result = await db.execute(
        select(APIKey).where(APIKey.user_id == current_user.id, APIKey.provider == data.provider)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.api_key = data.api_key
        await db.flush()
        return APIKeyResponse(
            id=existing.id,
            provider=existing.provider,
            key_preview=mask_key(existing.api_key),
            created_at=existing.created_at,
        )

    new_key = APIKey(provider=data.provider, api_key=data.api_key, user_id=current_user.id)
    db.add(new_key)
    await db.flush()
    await db.refresh(new_key)

    return APIKeyResponse(
        id=new_key.id,
        provider=new_key.provider,
        key_preview=mask_key(new_key.api_key),
        created_at=new_key.created_at,
    )


@router.delete("/{provider}")
async def delete_api_key(
    provider: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete the current user's API key for a provider."""
    result = await db.execute(
        delete(APIKey).where(APIKey.user_id == current_user.id, APIKey.provider == provider)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"No API key found for provider: {provider}")
    return {"message": f"API key for {provider} deleted"}


@router.get("/vision-models")
async def list_vision_models(current_user: User = Depends(get_current_user)):
    """Get the map of provider -> vision-capable (image input) models."""
    return get_vision_models()


@router.get("/models/{provider}")
async def list_models(
    provider: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get available models for a provider (built-in defaults plus the user's own custom models)."""
    models = get_models(provider)
    if not models:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    custom_result = await db.execute(
        select(CustomModel.model)
        .where(CustomModel.user_id == current_user.id, CustomModel.provider == provider)
        .order_by(CustomModel.created_at)
    )
    custom_models = [m for m in custom_result.scalars().all() if m not in models]

    return {"provider": provider, "models": models + custom_models}
