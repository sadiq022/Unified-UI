import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from backend.database import get_db
from backend.models import PanelPreset, User
from backend.schemas import PanelPresetCreate, PanelPresetResponse
from backend.auth import get_current_user

router = APIRouter(prefix="/api/panel-presets", tags=["Panel Presets"])


@router.get("", response_model=list[PanelPresetResponse])
async def list_presets(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """List the current user's saved panel presets."""
    result = await db.execute(
        select(PanelPreset).where(PanelPreset.user_id == current_user.id).order_by(PanelPreset.created_at)
    )
    return result.scalars().all()


@router.post("", response_model=PanelPresetResponse)
async def save_preset(
    data: PanelPresetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save the current panel configuration under a name (updates if the name already exists)."""
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Preset name is required")
    if not data.panels:
        raise HTTPException(status_code=400, detail="At least one panel is required")

    existing = await db.execute(
        select(PanelPreset).where(PanelPreset.user_id == current_user.id, PanelPreset.name == name)
    )
    preset = existing.scalar_one_or_none()

    if preset:
        preset.config = json.dumps(data.panels)
    else:
        preset = PanelPreset(user_id=current_user.id, name=name, config=json.dumps(data.panels))
        db.add(preset)

    await db.flush()
    await db.refresh(preset)
    return preset


@router.delete("/{preset_id}")
async def delete_preset(
    preset_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a saved panel preset."""
    result = await db.execute(
        delete(PanelPreset).where(PanelPreset.id == preset_id, PanelPreset.user_id == current_user.id)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Preset not found")
    return {"message": "Preset deleted"}
