"""路径 B（模拟面试）的业务编排服务。

本模块连接 HTTP/SSE 接口、可中断的 LangGraph 和业务数据库：Graph checkpoint
保存一次面试正在进行的短期状态，Conversation/Message 保存可跨登录查看的长期历史。
Service 负责用户所有权校验、同一会话并发控制、两类存储间的数据同步和响应模型转换。
"""
import asyncio
import logging
import uuid
from collections.abc import AsyncIterator

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.interview_graph import (
    get_interview_state,
    start_interview_graph,
    stream_interview_answer,
)
from app.memory.checkpoint import delete_checkpoint
from app.repositories import ConversationRepo
from app.schemas.interview import (
    InterviewFeedback,
    InterviewQuestion,
    InterviewResult,
    InterviewSessionResponse,
    InterviewStartRequest,
)
from app.services.knowledge_ingestion_service import KnowledgeIngestionService


# 每个 session_id 对应一把进程内锁，避免用户双击提交或多个请求同时恢复同一中断点。
# 该锁不跨 Python 进程；多 worker 部署时需要替换为数据库锁或分布式锁。
_session_locks: dict[str, asyncio.Lock] = {}
logger = logging.getLogger(__name__)


def _lock_for(session_id: str) -> asyncio.Lock:
    """获取指定面试会话的锁；首次访问时创建并缓存。"""
    return _session_locks.setdefault(session_id, asyncio.Lock())


def _question_response(state: dict) -> InterviewQuestion | None:
    """把 Graph 当前题目转换成前端使用的 Pydantic 响应模型。

    `current_index` 只统计基础题，因此追问沿用所属基础题的题号；`is_follow_up`
    和 `parent_question_id` 供 UI 将追问展示为“第 N 题追问”。没有当前题时返回 None。
    """
    question = state.get("current_question")
    if not question:
        return None
    return InterviewQuestion(
        question_id=question["question_id"],
        question_number=state.get("current_index", 0) + 1,
        question=question["question"],
        category=question.get("category"),
        difficulty=question.get("difficulty"),
        is_follow_up=bool(question.get("is_follow_up")),
        parent_question_id=question.get("parent_question_id"),
    )


def _feedback_response(feedback: dict | None) -> InterviewFeedback | None:
    """把一条 Graph feedback 字典转换为标准评分响应；空值返回 None。"""
    if not feedback:
        return None
    return InterviewFeedback(
        question_id=feedback.get("question_id"),
        question_number=feedback.get("question_number"),
        is_follow_up=bool(feedback.get("is_follow_up")),
        parent_question_id=feedback.get("parent_question_id"),
        question=feedback.get("question", ""),
        answer=feedback.get("answer", ""),
        difficulty=feedback.get("difficulty"),
        score=feedback.get("score", 0),
        strengths=feedback.get("strengths", []),
        improvements=feedback.get("improvements", []),
        model_answer=feedback.get("model_answer"),
        comments=feedback.get("comments", ""),
    )


def _result_response(state: dict) -> InterviewResult:
    """根据完整 Graph 状态组装最终面试报告。

    汇总结果来自 `state.result`，逐轮明细来自 `state.feedbacks`；转换失败产生的空项
    会被过滤，确保返回值始终符合 `InterviewResult` 的字段约束。
    """
    summary = state.get("result") or {}
    feedbacks = [_feedback_response(item) for item in state.get("feedbacks", [])]
    return InterviewResult(
        total_score=summary.get("total_score", 0),
        feedbacks=[item for item in feedbacks if item is not None],
        overall_assessment=summary.get("overall_assessment", ""),
        strengths=summary.get("strengths", []),
        areas_to_improve=summary.get("areas_to_improve", []),
        tips=summary.get("tips", []),
    )


def _session_response(state: dict, last_feedback: dict | None = None) -> InterviewSessionResponse:
    """把 checkpoint 状态转换为一次完整的面试会话响应。

    进行中时返回当前题；完成后隐藏当前题并附带最终报告。`last_feedback` 只用于
    回答提交后的即时反馈，不会取代状态中的完整 feedback 列表。
    """
    completed = state.get("status") == "completed"
    return InterviewSessionResponse(
        session_id=state["session_id"],
        interview_type=state["interview_type"],
        status="completed" if completed else "in_progress",
        current_question=None if completed else _question_response(state),
        current_question_index=state.get("current_index", 0),
        total_questions=state.get("total_questions", 0),
        result=_result_response(state) if completed else None,
        last_feedback=_feedback_response(last_feedback),
        answered_count=state.get("answered_count", 0),
    )


def _archive_payload(state: dict) -> dict:
    """生成可写入 Conversation metadata 的 JSON 安全面试归档。"""
    return _session_response(state).model_dump(mode="json")


def _response_from_archive(conversation) -> InterviewSessionResponse | None:
    """优先读取新版完整归档，否则尝试从旧版消息记录重建反馈。

    新版会话完成时会把完整 `InterviewSessionResponse` 放入 `interview_archive`。
    旧版只在 Conversation 中保存报告摘要，题目、回答和评分分散在 Message 中，
    因此需要按 user/assistant 消息顺序配对，并补齐题号及追问归属信息。
    """
    metadata = conversation.metadata_ or {}
    archive = metadata.get("interview_archive")
    if archive:
        return InterviewSessionResponse.model_validate(archive)

    # 兼容旧数据：Conversation 只有 result 摘要，每轮明细需要从 messages 还原。
    legacy_summary = metadata.get("result")
    if not legacy_summary:
        return None

    feedbacks: list[InterviewFeedback] = []
    pending_user = None
    base_number = 0
    for message in conversation.messages:
        # 一条 user 回答应与它后面的 assistant 评分配成同一轮。
        if message.role == "user":
            pending_user = message
            continue
        if message.role != "assistant" or not message.metadata_:
            continue

        item = dict(message.metadata_)
        user_meta = (pending_user.metadata_ or {}) if pending_user else {}
        is_follow_up = bool(item.get("is_follow_up", user_meta.get("is_follow_up", False)))
        if not is_follow_up:
            base_number += 1
        item.setdefault("question", user_meta.get("question", ""))
        item.setdefault("answer", pending_user.content if pending_user else "")
        item.setdefault("question_id", user_meta.get("question_id"))
        item.setdefault("question_number", user_meta.get("question_number") or max(base_number, 1))
        item.setdefault("is_follow_up", is_follow_up)
        parsed = _feedback_response(item)
        if parsed:
            feedbacks.append(parsed)
        pending_user = None

    result = InterviewResult(
        total_score=legacy_summary.get("total_score", 0),
        feedbacks=feedbacks,
        overall_assessment=legacy_summary.get("overall_assessment", ""),
        strengths=legacy_summary.get("strengths", []),
        areas_to_improve=legacy_summary.get("areas_to_improve", []),
        tips=legacy_summary.get("tips", []),
    )
    return InterviewSessionResponse(
        session_id=conversation.thread_id,
        interview_type=conversation.agent_type or "mixed",
        status="completed",
        current_question_index=len([
            item for item in feedbacks if not item.is_follow_up
        ]),
        total_questions=len([
            item for item in feedbacks if not item.is_follow_up
        ]),
        result=result,
        answered_count=len(feedbacks),
        created_at=conversation.created_at,
    )


async def _persist_answer_result(
    db: AsyncSession,
    conversation,
    before: dict,
    state: dict,
    answer: str,
    feedback_count: int,
) -> dict | None:
    """持久化刚完成的一轮回答，并在面试结束时生成完整归档。

    `feedback_count` 是恢复 Graph 前已有的反馈数量；恢复后新增的第一项就是本轮评分。
    用户回答和 assistant 评分分别保存为 Message，便于历史兼容和逐轮展示。若状态已
    completed，还会把完整会话快照写入 Conversation metadata。返回本轮最新 feedback。
    """
    feedbacks = state.get("feedbacks", [])
    latest = feedbacks[feedback_count] if len(feedbacks) > feedback_count else None
    await ConversationRepo.create_message(
        db, conversation_id=conversation.id, role="user", content=answer,
        metadata_={
            "question": before["current_question"]["question"],
            "question_id": before["current_question"]["question_id"],
            "is_follow_up": before.get("is_follow_up", False),
        },
    )
    if latest:
        await ConversationRepo.create_message(
            db, conversation_id=conversation.id, role="assistant",
            content=f"Score: {latest.get('score', 0)}/10 - {latest.get('comments', '')}",
            metadata_=latest,
        )
    if state.get("status") == "completed":
        conversation.metadata_ = {
            **(conversation.metadata_ or {}),
            "interview_archive": _archive_payload(state),
        }
    return latest


class InterviewService:
    """路径 B 的会话生命周期与持久化业务入口。"""

    @staticmethod
    async def start_session(
        db: AsyncSession,
        user_id: str,
        data: InterviewStartRequest,
    ) -> InterviewSessionResponse:
        """创建业务会话，并启动 Graph 运行到第一道题的 interrupt。

        `session_id` 同时作为 Conversation.thread_id 和 LangGraph checkpoint thread_id，
        用来关联长期历史与短期运行状态。首次出题失败时清理 checkpoint，并向 API 返回
        502；成功时返回当前题，但不在此处等待用户回答。
        """
        session_id = str(uuid.uuid4())
        # 先创建长期历史的会话主记录，后续每轮回答和评分都关联到该 Conversation。
        await ConversationRepo.create(
            db,
            user_id=user_id,
            title=f"{data.interview_type.upper()} Interview - {data.job_title or 'General'}",
            agent_type=data.interview_type,
            thread_id=session_id,
        )
        try:
            # Graph 内部完成状态初始化、第一题生成，并停在 wait_for_answer 中断点。
            state = await start_interview_graph(
                user_id=user_id,
                session_id=session_id,
                interview_type=data.interview_type,
                target_position=data.job_title,
                question_mode=data.question_mode,
                difficulty=data.difficulty,
                total_questions=data.question_count,
            )
        except Exception as exc:
            logger.exception(
                "Interview start failed session_id=%s type=%s",
                session_id, data.interview_type,
            )
            await delete_checkpoint(session_id)
            raise HTTPException(status_code=502, detail="生成面试题失败，请稍后重试") from exc
        if not state or not state.get("current_question"):
            await delete_checkpoint(session_id)
            raise HTTPException(status_code=502, detail="未能生成面试题")
        # 把本轮新增的基础题同步到 SQL 与 Chroma；追问依赖具体回答，不进入公共题库。
        await KnowledgeIngestionService.ingest_questions(
            db, state.get("questions") or []
        )
        logger.info(
            "Interview started session_id=%s type=%s total_questions=%d",
            session_id, data.interview_type, data.question_count,
        )
        return _session_response(state)

    @staticmethod
    async def stream_answer(
        db: AsyncSession, user_id: str, session_id: str, answer: str,
    ) -> AsyncIterator[dict]:
        """提交一个回答，恢复路径 B，并返回供 SSE 消费的异步事件流。

        返回流之前先校验会话所有权、checkpoint 状态并获得 session 锁。真正的 Graph
        恢复发生在内部 `event_stream()` 被 API 迭代时；它转发 custom 进度事件，执行完后
        持久化本轮消息并追加 `session_updated/session_completed`。无论成功或失败都会释放锁。
        """
        conversation = await ConversationRepo.get_by_thread_and_user(db, session_id, user_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Interview session not found")

        lock = _lock_for(session_id)
        await lock.acquire()
        try:
            before = await get_interview_state(session_id)
            if not before:
                raise HTTPException(status_code=404, detail="Interview checkpoint not found")
            if before.get("status") == "completed":
                raise HTTPException(status_code=400, detail="Interview already completed")
            if before.get("status") != "waiting_answer":
                raise HTTPException(status_code=409, detail="Interview is not waiting for an answer")
        except Exception:
            lock.release()
            raise

        feedback_count = len(before.get("feedbacks", []))

        async def event_stream() -> AsyncIterator[dict]:
            """消费 Graph custom stream，完成持久化并保证最终释放会话锁。"""
            try:
                # Command(resume=answer) 等 LangGraph 细节已封装在 Graph 层公开入口中。
                async for event in stream_interview_answer(session_id, answer):
                    yield event

                state = await get_interview_state(session_id)
                if not state:
                    raise RuntimeError("Interview state unavailable")
                previous_question_count = len(before.get("questions") or [])
                await KnowledgeIngestionService.ingest_questions(
                    db, (state.get("questions") or [])[previous_question_count:]
                )
                latest = await _persist_answer_result(
                    db, conversation, before, state, answer, feedback_count
                )
                logger.info(
                    "Interview answer processed session_id=%s question_index=%d status=%s",
                    session_id,
                    before.get("current_index", 0),
                    state.get("status"),
                )
                yield {
                    "type": "session_completed" if state.get("status") == "completed" else "session_updated",
                    "message": "面试完成" if state.get("status") == "completed" else "可以继续作答",
                    "session": _session_response(state, latest).model_dump(mode="json"),
                }
            except Exception as exc:
                # SSE 已开始后不能再改变 HTTP 状态码，因此把运行异常编码为 error 事件。
                await db.rollback()
                logger.exception("Interview answer stream failed for %s", session_id)
                yield {"type": "error", "message": "面试处理失败，本题状态已保留，请重新提交"}
            finally:
                lock.release()

        return event_stream()

    @staticmethod
    async def get_feedback(
        db: AsyncSession, user_id: str, session_id: str,
    ) -> InterviewSessionResponse:
        """读取当前用户的一次面试详情或最终报告。

        优先读取业务库中的完整归档，以保证服务重启或 checkpoint 清理后历史仍可访问；
        未归档的进行中会话再读取最新 checkpoint。两处都没有时返回 404。
        """
        conversation = await ConversationRepo.get_by_thread_and_user(db, session_id, user_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Interview session not found")
        archived = _response_from_archive(conversation)
        if archived:
            return archived
        state = await get_interview_state(session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Interview checkpoint not found")
        return _session_response(state)

    @staticmethod
    async def list_sessions(db: AsyncSession, user_id: str) -> dict:
        """列出当前用户的面试历史摘要，并判断每个会话的可用状态。

        已归档记录直接使用归档状态；未归档记录检查 checkpoint，分别标记为
        `in_progress`、`completed` 或 `unavailable`。列表不返回题目和报告正文。
        """
        conversations = await ConversationRepo.list_interview_sessions(db, user_id)
        sessions = []
        for conv in conversations:
            archived = _response_from_archive(conv)
            if archived:
                session_status = archived.status
            else:
                state = await get_interview_state(conv.thread_id)
                session_status = (
                    "completed" if state and state.get("status") == "completed"
                    else "in_progress" if state
                    else "unavailable"
                )
            sessions.append({
                "session_id": conv.thread_id,
                "title": conv.title,
                "type": conv.agent_type,
                "status": session_status,
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
            })
        return {"sessions": sessions, "total": len(sessions)}

    @staticmethod
    async def delete_session(
        db: AsyncSession, user_id: str, session_id: str,
    ) -> None:
        """删除当前用户的面试业务历史、checkpoint 和进程内会话锁。

        Conversation 删除会通过 ORM 级联清理 Messages；随后删除相同 session_id 的
        LangGraph 状态，避免遗留短期记忆。所有权校验失败时返回 404。
        """
        conversation = await ConversationRepo.get_by_thread_and_user(db, session_id, user_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Interview session not found")
        await ConversationRepo.delete(db, conversation)
        await delete_checkpoint(session_id)
        _session_locks.pop(session_id, None)
