# CareerMind AI Resume Repository — 简历表数据访问
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.resume import Resume


class ResumeRepo:
    @staticmethod
    async def list_completed_by_user(
        db: AsyncSession,
        user_id: str,
        limit: int = 5,
    ) -> list[Resume]:
        """按时间倒序读取用户已完成分析的简历。"""
        result = await db.execute(
            select(Resume)
            .where(Resume.user_id == user_id, Resume.status == "completed")
            .order_by(Resume.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id_and_user(
        db: AsyncSession,
        resume_id: str,
        user_id: str,
    ) -> Resume | None:
        result = await db.execute(
            select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        user_id: str,
        original_filename: str,
        file_path: str,
        file_type: str,
        status: str = "pending",
    ) -> Resume:
        """创建简历记录并 flush，返回 ORM 对象（后续字段修改/flush 由 service 进行）。"""
        resume = Resume(
            user_id=user_id,
            original_filename=original_filename,
            file_path=file_path,
            file_type=file_type,
            status=status,
        )
        db.add(resume)
        await db.flush()
        return resume
