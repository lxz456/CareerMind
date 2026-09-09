# CareerMind AI Users API
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.user import (
    UserProfileResponse,
    UserProfileUpdateRequest,
)
from app.services.user_service import UserService
from app.utils.security import get_current_user_id

router = APIRouter(prefix="/api/v1/users", tags=["Users"])

@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's profile."""
    return await UserService.get_profile(db, user_id)

@router.put("/me", response_model=UserProfileResponse)
async def update_my_profile(
    data: UserProfileUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Update current user's profile."""
    return await UserService.update_profile(db, user_id, data)
