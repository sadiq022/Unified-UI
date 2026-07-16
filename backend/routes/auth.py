from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.database import get_db
from backend.models import User
from backend.schemas import UserSignup, UserLogin, TokenResponse
from backend.auth import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/signup", response_model=TokenResponse)
async def signup(data: UserSignup, db: AsyncSession = Depends(get_db)):
    """Create a new account and log in immediately."""
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    user = User(email=data.email, password_hash=hash_password(data.password))
    db.add(user)
    await db.flush()
    await db.refresh(user)

    token, expires_at = create_access_token(user.id)
    return TokenResponse(access_token=token, expires_at=expires_at, user=user)


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    email = data.email.strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token, expires_at = create_access_token(user.id)
    return TokenResponse(access_token=token, expires_at=expires_at, user=user)


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "email": current_user.email}
