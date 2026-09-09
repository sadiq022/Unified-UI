"""Search API routes: config and standalone search endpoint."""

from fastapi import APIRouter, Depends
from backend.auth import get_current_user
from backend.models import User
from backend.services.search.core import get_search_config

router = APIRouter(prefix="/api/search", tags=["Search"])


@router.get("/config")
async def search_config(current_user: User = Depends(get_current_user)):
    """Return current search provider configuration."""
    return get_search_config()
