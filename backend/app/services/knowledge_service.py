"""知识中心刷新、Hybrid Search 和 Rerank 用例编排。"""
import asyncio
import logging

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.llm.reranker import rerank_documents
from app.repositories import KnowledgeRepo, VectorKnowledgeRepo
from app.schemas.knowledge import (
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    QuestionItem,
    ResourceItem,
)
from app.services.knowledge_ingestion_service import (
    KnowledgeIngestionResult,
    KnowledgeIngestionService,
)
from app.tools.learning_resources import collect_learning_resource_cards


logger = logging.getLogger(__name__)


class KnowledgeService:
    """知识刷新与检索的业务入口。"""

    @staticmethod
    async def _refresh(
        db: AsyncSession, req: KnowledgeSearchRequest
    ) -> KnowledgeIngestionResult:
        """按请求类型生成/采集新内容并统一双写，返回处理数量。"""
        if req.type == "interview":
            from app.llm.interview_questions import generate_questions_by_llm

            interview_type = {
                "behavioral": "hr",
                "system_design": "system_design",
            }.get(req.category, "technical")
            cards = await generate_questions_by_llm(
                interview_type=interview_type,
                target_position=req.query,
                skills=[],
                question_count=req.limit,
            )
            for card in cards:
                if req.category:
                    card["category"] = req.category
                card["difficulty"] = req.difficulty or card.get("difficulty", "medium")
            return await KnowledgeIngestionService.ingest_questions(db, cards)

        cards = await collect_learning_resource_cards(req.query)
        return await KnowledgeIngestionService.ingest_resources(db, cards)

    @staticmethod
    async def search_knowledge(
        db: AsyncSession,
        req: KnowledgeSearchRequest,
    ) -> KnowledgeSearchResponse:
        """并行执行 BM25 与向量召回，经 RRF 融合、去重和 Rerank 返回 Top 20。"""
        refreshed = False
        if req.refresh:
            try:
                refreshed = bool(await KnowledgeService._refresh(db, req))
            except Exception as exc:
                logger.warning("Knowledge refresh failed; using cached data: %s", exc)

        settings = get_settings()
        candidate_limit = max(1, settings.HYBRID_CANDIDATE_LIMIT)
        bm25_task = KnowledgeService._bm25_recall(db, req, candidate_limit)
        vector_task = KnowledgeService._vector_recall(req, candidate_limit)
        bm25_result, vector_result = await asyncio.gather(
            bm25_task, vector_task, return_exceptions=True
        )

        if isinstance(bm25_result, asyncio.CancelledError):
            raise bm25_result
        if isinstance(vector_result, asyncio.CancelledError):
            raise vector_result

        bm25_available = not isinstance(bm25_result, Exception)
        vector_available = not isinstance(vector_result, Exception)
        if not bm25_available:
            logger.warning("BM25 knowledge recall failed: %s", bm25_result)
            bm25_result = []
        if not vector_available:
            logger.warning("Vector knowledge recall failed: %s", vector_result)
            vector_result = []
        if not bm25_available and not vector_available:
            raise HTTPException(status_code=503, detail="知识库暂时不可用")

        candidates = KnowledgeService._rrf_fuse_candidates(
            req.type,
            bm25_result,
            vector_result,
            rrf_k=settings.HYBRID_RRF_K,
        )[:candidate_limit]

        final_limit = max(1, min(req.limit, settings.RERANK_FINAL_LIMIT, 20))
        ranked = await KnowledgeService._rerank_or_fallback(
            req.query, candidates, final_limit
        )
        return KnowledgeSearchResponse(
            type=req.type,
            results=ranked,
            from_cache=not refreshed,
        )

    @staticmethod
    async def _bm25_recall(
        db: AsyncSession,
        req: KnowledgeSearchRequest,
        limit: int,
    ) -> list[dict]:
        """调用关系数据库 Repository 执行 FTS5 BM25 召回。"""
        if req.type == "interview":
            return await KnowledgeRepo.search_questions_bm25(
                db,
                query=req.query,
                category=req.category,
                difficulty=req.difficulty,
                limit=limit,
            )
        return await KnowledgeRepo.search_resources_bm25(
            db,
            query=req.query,
            item_type=req.category,
            limit=limit,
        )

    @staticmethod
    async def _vector_recall(
        req: KnowledgeSearchRequest,
        limit: int,
    ) -> list[dict]:
        """调用向量 Repository 执行 Chroma 语义召回。"""
        if req.type == "interview":
            return await VectorKnowledgeRepo.search_questions(
                req.query,
                top_k=limit,
                category=req.category,
                difficulty=req.difficulty,
            )
        return await VectorKnowledgeRepo.search_resources(
            req.query,
            top_k=limit,
            resource_type=req.category,
        )

    @staticmethod
    def _rrf_fuse_candidates(
        content_type: str,
        bm25_hits: list[dict],
        vector_hits: list[dict],
        *,
        rrf_k: int,
    ) -> list[dict]:
        """按稳定 ID 合并两路排名，以 RRF 分数产生精排候选顺序。"""
        rrf_k = max(1, rrf_k)
        merged: dict[str, dict] = {}

        for source, hits in (("bm25", bm25_hits), ("vector", vector_hits)):
            seen_ids: set[str] = set()
            for rank, hit in enumerate(hits, start=1):
                item = (
                    KnowledgeService._to_item(content_type, hit["item"])
                    if source == "bm25"
                    else KnowledgeService._vector_hit_to_item(content_type, hit)
                )
                if item.id in seen_ids:
                    continue
                seen_ids.add(item.id)

                candidate = merged.get(item.id)
                if candidate is None:
                    candidate = {
                        "item": item,
                        "document": KnowledgeService._item_document(item),
                        "rrf_score": 0.0,
                        "best_rank": rank,
                    }
                    merged[item.id] = candidate
                elif source == "bm25":
                    # SQL 业务记录比向量 metadata 完整，合并时优先保留它。
                    candidate["item"] = item
                    candidate["document"] = KnowledgeService._item_document(item)

                candidate["rrf_score"] += 1.0 / (rrf_k + rank)
                candidate["best_rank"] = min(candidate["best_rank"], rank)

        return sorted(
            merged.values(),
            key=lambda candidate: (
                -candidate["rrf_score"],
                candidate["best_rank"],
                candidate["item"].id,
            ),
        )

    @staticmethod
    async def _rerank_or_fallback(
        query: str,
        candidates: list[dict],
        final_limit: int,
    ) -> list[QuestionItem | ResourceItem]:
        """使用本地 BGE 精排；模型不可用时按 RRF 排名稳定降级。"""
        if not candidates:
            return []

        try:
            reranked = await rerank_documents(
                query,
                [candidate["document"] for candidate in candidates],
                final_limit,
            )
            if reranked:
                results = []
                for rank in reranked:
                    item = candidates[rank["index"]]["item"]
                    item.score = min(max(rank["score"], 0.0), 1.0)
                    results.append(item)
                return results
        except Exception as exc:
            logger.warning("BGE rerank failed; using RRF ranking: %s", exc)

        # RRF 原始分数用于排序而非相关度展示；降级响应按最高分缩放到 0～1。
        max_rrf_score = max(candidate["rrf_score"] for candidate in candidates) or 1.0
        results = []
        for candidate in candidates[:final_limit]:
            item = candidate["item"]
            item.score = candidate["rrf_score"] / max_rrf_score
            results.append(item)
        return results

    @staticmethod
    def _item_document(item: QuestionItem | ResourceItem) -> str:
        if isinstance(item, QuestionItem):
            return "\n".join([
                item.question,
                item.topic or "",
                " ".join(item.expected_points),
            ])
        return "\n".join([
            item.name,
            item.topic or "",
            item.description or "",
            item.type or "",
        ])

    @staticmethod
    def _vector_hit_to_item(
        content_type: str,
        candidate: dict,
    ) -> QuestionItem | ResourceItem:
        metadata = candidate.get("metadata", {}) or {}
        if content_type == "interview":
            return QuestionItem(
                id=candidate["id"],
                question=metadata.get("question")
                or (candidate.get("document") or "").split("\n", 1)[0],
                category=metadata.get("category"),
                difficulty=metadata.get("difficulty"),
                topic=metadata.get("topic"),
                expected_points=[],
            )
        return ResourceItem(
            id=candidate["id"],
            name=metadata.get("name") or "",
            type=metadata.get("type"),
            url=metadata.get("url"),
            topic=metadata.get("topic"),
            description=metadata.get("description"),
        )

    @staticmethod
    def _to_item(content_type: str, obj) -> QuestionItem | ResourceItem:
        if content_type == "interview":
            return QuestionItem(
                id=obj.id,
                question=obj.question,
                category=obj.category,
                difficulty=obj.difficulty,
                topic=obj.topic,
                expected_points=obj.expected_points or [],
                created_at=obj.created_at,
            )
        return ResourceItem(
            id=obj.id,
            name=obj.name,
            type=obj.type,
            url=obj.url,
            topic=obj.topic,
            description=obj.description,
            created_at=obj.created_at,
        )
