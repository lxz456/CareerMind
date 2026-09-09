# CareerMind AI User Repository — 用户表数据访问
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepo:
    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: str) -> User | None:
        return await db.get(User, user_id)

    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> User | None:
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_username(db: AsyncSession, username: str) -> User | None:
        result = await db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_username_or_email(db: AsyncSession, value: str) -> User | None:
        """登录用：username 或 email 二选一匹配。"""
        result = await db.execute(
            select(User).where((User.username == value) | (User.email == value))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        email: str,
        username: str,
        hashed_password: str,
    ) -> User:
        user = User(email=email, username=username, hashed_password=hashed_password)
        db.add(user)
        await db.flush()
        return user
