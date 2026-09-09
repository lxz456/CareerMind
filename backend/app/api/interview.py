# CareerMind AI Interview API
import json

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.interview import (
    InterviewStartRequest,
    InterviewAnswerRequest,
    InterviewSessionResponse,
    InterviewSessionListResponse,
)
from app.services.interview_service import InterviewService
from app.utils.security import get_current_user_id

router = APIRouter(prefix="/api/v1/interview", tags=["Interview"])

@router.post("/start", response_model=InterviewSessionResponse, status_code=201)
async def start_interview(
    data: InterviewStartRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Start a new mock interview session."""
    return await InterviewService.start_session(db, user_id, data)

@router.post("/{session_id}/answer")
async def stream_answer(
    session_id: str,
    data: InterviewAnswerRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Submit an answer and stream Path B business events as SSE."""
    events = await InterviewService.stream_answer(db, user_id, session_id, data.answer)

    async def encode_events():
        async for event in events:
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        encode_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

@router.get("/{session_id}/feedback", response_model=InterviewSessionResponse)
async def get_feedback(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get the complete feedback for a (completed) interview session."""
    return await InterviewService.get_feedback(db, user_id, session_id)

@router.get("/sessions", response_model=InterviewSessionListResponse)
async def list_sessions(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List all interview sessions for the current user."""
    return await InterviewService.list_sessions(db, user_id)

@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """删除一条面试历史记录。"""
    await InterviewService.delete_session(db, user_id, session_id)
    return Response(status_code=204)
