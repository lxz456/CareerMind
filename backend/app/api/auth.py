# CareerMind AI Auth API
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.user import UserRegisterRequest, UserLoginRequest, TokenResponse
from app.services.user_service import UserService

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(data: UserRegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user account."""
    return await UserService.register(db, data)

@router.post("/login", response_model=TokenResponse)
async def login(data: UserLoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with username/email and password."""
    return await UserService.login(db, data)
