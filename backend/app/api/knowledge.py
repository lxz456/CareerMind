# CareerMind AI Knowledge API
# 题库 / 学习中心：Tavily 实时搜 + 分层检索（SQL 粗筛 + 向量精排）
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.knowledge import (
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
)
from app.services.knowledge_service import KnowledgeService
from app.utils.security import get_current_user_id

router = APIRouter(prefix="/api/v1/knowledge", tags=["Knowledge"])


@router.post("/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    data: KnowledgeSearchRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """搜索题库/学习资料；新题由 LLM 生成，学习资料由 Tavily 采集。"""
    return await KnowledgeService.search_knowledge(db, data)
