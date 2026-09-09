# CareerMind AI User Service
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.repositories import UserRepo
from app.utils.security import hash_password, verify_password, create_access_token
from app.schemas.user import (
    UserRegisterRequest,
    UserLoginRequest,
    UserProfileUpdateRequest,
    TokenResponse,
    UserProfileResponse,
)

class UserService:
    @staticmethod
    async def register(db: AsyncSession, data: UserRegisterRequest) -> TokenResponse:
        """Register a new user."""
        # Check for existing email
        if await UserRepo.get_by_email(db, data.email):
            raise HTTPException(status_code=400, detail="Email already registered")

        # Check for existing username
        if await UserRepo.get_by_username(db, data.username):
            raise HTTPException(status_code=400, detail="Username already taken")

        user = await UserRepo.create(
            db,
            email=data.email,
            username=data.username,
            hashed_password=hash_password(data.password),
        )

        token = create_access_token(user.id, user.email)
        return TokenResponse(
            access_token=token,
            user_id=user.id,
            username=user.username,
        )

    @staticmethod
    async def login(db: AsyncSession, data: UserLoginRequest) -> TokenResponse:
        """Authenticate user and return JWT."""
        # Try username first, then email
        user = await UserRepo.get_by_username_or_email(db, data.username)
        if not user or not verify_password(data.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account is deactivated")

        token = create_access_token(user.id, user.email)
        return TokenResponse(
            access_token=token,
            user_id=user.id,
            username=user.username,
        )

    @staticmethod
    async def get_profile(db: AsyncSession, user_id: str) -> UserProfileResponse:
        """Get user profile by ID."""
        user = await UserRepo.get_by_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return UserProfileResponse.model_validate(user)

    @staticmethod
    async def update_profile(
        db: AsyncSession, user_id: str, data: UserProfileUpdateRequest
    ) -> UserProfileResponse:
        """Update user profile."""
        user = await UserRepo.get_by_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(user, key, value)

        await db.flush()
        return UserProfileResponse.model_validate(user)
