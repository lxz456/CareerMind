"""供未来 Agent 上下文使用的跨会话业务历史聚合器。

该模块不直接编写 SQL；所有持久化读取都通过 Repository 完成。目前主流程尚未调用
LongTermMemory，因此它是预留能力，不应与 LangGraph checkpoint 短期记忆混淆。
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.conversation_repo import ConversationRepo
from app.repositories.resume_repo import ResumeRepo
from app.repositories.user_repo import UserRepo
from app.repositories.workflow_repo import WorkflowRepo


class LongTermMemory:
    """把用户资料与跨会话历史整理成适合 Agent 使用的轻量上下文。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_profile_summary(self, user_id: str) -> dict:
        """返回用户职业目标和经验概况。"""
        user = await UserRepo.get_by_id(self.db, user_id)
        if not user:
            return {}
        return {
            "user_id": user.id,
            "name": user.full_name or user.username,
            "career_goal": user.career_goal,
            "target_industry": user.target_industry,
            "years_of_experience": user.years_of_experience,
            "current_level": user.current_level,
        }

    async def get_resume_history(self, user_id: str, limit: int = 5) -> list[dict]:
        """返回用户最近完成的简历分析摘要。"""
        resumes = await ResumeRepo.list_completed_by_user(self.db, user_id, limit)
        return [
            {
                "id": resume.id,
                "filename": resume.original_filename,
                "score": resume.analysis_score,
                "skills": (resume.parsed_data or {}).get("skills", []),
                "created_at": (
                    resume.created_at.isoformat() if resume.created_at else None
                ),
            }
            for resume in resumes
        ]

    async def get_learning_progress(self, user_id: str) -> dict:
        """根据已完成工作流汇总职业规划学习进度。"""
        runs = await WorkflowRepo.list_completed_by_user(self.db, user_id, limit=10)
        plans = [
            {
                "run_id": run.id,
                "target": run.career_plan_result.get("target_position"),
                "total_months": run.career_plan_result.get("total_months"),
            }
            for run in runs
            if run.career_plan_result
        ]
        return {
            "total_workflows": len(runs),
            "completed_career_plans": plans,
            "latest_plan": plans[0] if plans else None,
        }

    async def get_interview_history(self, user_id: str) -> list[dict]:
        """返回用户最近二十次模拟面试摘要。"""
        conversations = await ConversationRepo.list_interview_sessions(
            self.db, user_id, limit=20
        )
        return [
            {
                "id": conversation.id,
                "title": conversation.title,
                "type": conversation.agent_type,
                "created_at": (
                    conversation.created_at.isoformat()
                    if conversation.created_at
                    else None
                ),
            }
            for conversation in conversations
        ]
