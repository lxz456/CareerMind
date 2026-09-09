# CareerMind AI Workflow Repository — 工作流/职业规划表数据访问
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import WorkflowRun


class WorkflowRepo:
    @staticmethod
    async def list_completed_by_user(
        db: AsyncSession,
        user_id: str,
        limit: int = 10,
    ) -> list[WorkflowRun]:
        """按时间倒序读取用户已完成的工作流。"""
        result = await db.execute(
            select(WorkflowRun)
            .where(WorkflowRun.user_id == user_id, WorkflowRun.status == "completed")
            .order_by(WorkflowRun.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_running_career_plans(db: AsyncSession) -> list[WorkflowRun]:
        result = await db.execute(
            select(WorkflowRun).where(
                WorkflowRun.workflow_type == "career_planning",
                WorkflowRun.status == "running",
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        run_id: str,
    ) -> WorkflowRun | None:
        return await db.get(WorkflowRun, run_id)

    @staticmethod
    async def get_by_id_and_user(
        db: AsyncSession,
        run_id: str,
        user_id: str,
    ) -> WorkflowRun | None:
        result = await db.execute(
            select(WorkflowRun).where(WorkflowRun.id == run_id, WorkflowRun.user_id == user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_plan_by_id_and_user(
        db: AsyncSession,
        run_id: str,
        user_id: str,
    ) -> WorkflowRun | None:
        """查 careary_planning 类型的工作流（用于删除历史记录）。"""
        result = await db.execute(
            select(WorkflowRun).where(
                WorkflowRun.id == run_id,
                WorkflowRun.user_id == user_id,
                WorkflowRun.workflow_type == "career_planning",
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_career_plans(
        db: AsyncSession,
        user_id: str,
    ) -> list[WorkflowRun]:
        result = await db.execute(
            select(WorkflowRun)
            .where(WorkflowRun.user_id == user_id, WorkflowRun.workflow_type == "career_planning")
            .order_by(WorkflowRun.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        user_id: str,
        workflow_type: str,
        status: str,
        current_step: str | None,
        completed_steps: list[str] | None,
        input_data: dict | None,
        progress: float,
    ) -> WorkflowRun:
        run = WorkflowRun(
            user_id=user_id,
            workflow_type=workflow_type,
            status=status,
            current_step=current_step,
            completed_steps=completed_steps or [],
            input_data=input_data or {},
            progress=progress,
        )
        db.add(run)
        await db.flush()
        return run

    @staticmethod
    async def delete(db: AsyncSession, run: WorkflowRun) -> None:
        await db.delete(run)
        await db.flush()
