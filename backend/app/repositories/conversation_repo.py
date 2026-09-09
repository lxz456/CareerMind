# CareerMind AI Conversation Repository — 会话/消息表数据访问
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, Message

# 模拟面试类型（用于过滤"面试历史"）
_INTERVIEW_AGENT_TYPES = ["hr", "technical", "system_design", "mixed"]


class ConversationRepo:
    @staticmethod
    async def get_by_thread_and_user(
        db: AsyncSession,
        thread_id: str,
        user_id: str,
    ) -> Conversation | None:
        """按线程 id + 用户定位会话，且限定为模拟面试类型。"""
        result = await db.execute(
            select(Conversation).where(
                Conversation.thread_id == thread_id,
                Conversation.user_id == user_id,
                Conversation.agent_type.in_(_INTERVIEW_AGENT_TYPES),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_interview_sessions(
        db: AsyncSession,
        user_id: str,
        limit: int | None = None,
    ) -> list[Conversation]:
        statement = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .where(Conversation.agent_type.in_(_INTERVIEW_AGENT_TYPES))
            .order_by(Conversation.created_at.desc())
        )
        if limit is not None:
            statement = statement.limit(limit)
        result = await db.execute(statement)
        return list(result.scalars().all())

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        user_id: str,
        title: str,
        agent_type: str,
        thread_id: str,
    ) -> Conversation:
        conversation = Conversation(
            user_id=user_id,
            title=title,
            agent_type=agent_type,
            thread_id=thread_id,
        )
        db.add(conversation)
        await db.flush()
        return conversation

    @staticmethod
    async def create_message(
        db: AsyncSession,
        *,
        conversation_id: str,
        role: str,
        content: str,
        metadata_: dict | None = None,
    ) -> Message:
        """新增一条会话消息（字段级构造，service 不接触 ORM 对象）。"""
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata_=metadata_,
        )
        db.add(msg)
        await db.flush()
        return msg

    @staticmethod
    async def delete(db: AsyncSession, conv: Conversation) -> None:
        # cascade=all, delete-orphan 会一并删除其 messages
        await db.delete(conv)
        await db.flush()
