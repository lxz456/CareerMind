"""面试题和学习资料的统一双入库用例。"""
import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import KnowledgeRepo, VectorKnowledgeRepo


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KnowledgeIngestionResult:
    """一次双入库的结果，区分关系库成功和向量索引成功。"""

    unique_count: int = 0
    relational_created: int = 0
    vector_indexed: int = 0

    @property
    def vector_failed(self) -> int:
        """本次未成功写入向量库的条目数。"""
        return max(0, self.unique_count - self.vector_indexed)

    @property
    def fully_indexed(self) -> bool:
        """是否至少处理了一条数据，且全部完成双入库。"""
        return self.unique_count > 0 and self.vector_failed == 0

    def __bool__(self) -> bool:
        return self.fully_indexed


class KnowledgeIngestionService:
    """协调关系数据库元数据与 Chroma 语义索引的一致写入。"""

    @staticmethod
    async def ingest_questions(
        db: AsyncSession, cards: list[dict]
    ) -> KnowledgeIngestionResult:
        """按稳定内容 ID 去重并写入题目 SQL/Chroma，返回双入库结果。"""
        if not cards:
            return KnowledgeIngestionResult()

        vector_cards = []
        seen_ids = set()
        relational_created = 0
        for card in cards:
            if not str(card.get("question", "")).strip():
                continue
            question_id = VectorKnowledgeRepo.question_id(card)
            if question_id in seen_ids:
                continue
            seen_ids.add(question_id)
            if not await KnowledgeRepo.get_question_by_id(db, question_id):
                await KnowledgeRepo.create_question(
                    db,
                    id=question_id,
                    question=card.get("question", ""),
                    category=card.get("category"),
                    difficulty=card.get("difficulty"),
                    topic=card.get("topic"),
                    expected_points=card.get("expected_points", []) or [],
                )
                relational_created += 1
            vector_cards.append({**card, "knowledge_id": question_id})

        await db.flush()
        vector_indexed = 0
        if vector_cards:
            try:
                vector_indexed = await VectorKnowledgeRepo.upsert_questions(vector_cards)
            except Exception:
                # SQL 是业务数据源；向量索引异常时仍保留可被 BM25 召回的数据。
                logger.exception(
                    "Question vector indexing failed: unique=%d, relational_created=%d, vector_failed=%d",
                    len(vector_cards),
                    relational_created,
                    len(vector_cards),
                )
        return KnowledgeIngestionResult(
            unique_count=len(vector_cards),
            relational_created=relational_created,
            vector_indexed=vector_indexed,
        )

    @staticmethod
    async def ingest_resources(
        db: AsyncSession, cards: list[dict]
    ) -> KnowledgeIngestionResult:
        """按稳定内容 ID 去重并写入资源 SQL/Chroma，返回双入库结果。"""
        if not cards:
            return KnowledgeIngestionResult()

        vector_cards = []
        seen_ids = set()
        seen_urls = set()
        relational_created = 0
        for card in cards:
            if not str(card.get("name", "")).strip():
                continue
            url = str(card.get("url", "")).strip()
            normalized_url = url.casefold()
            if normalized_url and normalized_url in seen_urls:
                continue
            if normalized_url:
                seen_urls.add(normalized_url)

            resource_id = VectorKnowledgeRepo.resource_id(card)
            existing = await KnowledgeRepo.get_resource_by_id(db, resource_id)
            if not existing and url:
                existing = await KnowledgeRepo.get_resource_by_url(db, url)
            if existing:
                # 标题发生轻微变化但 URL 相同，沿用已有 SQL/Chroma 稳定 ID。
                resource_id = existing.id
            if resource_id in seen_ids:
                continue
            seen_ids.add(resource_id)
            if not existing:
                await KnowledgeRepo.create_resource(
                    db,
                    id=resource_id,
                    name=card.get("name", ""),
                    type=card.get("type"),
                    url=url or None,
                    topic=card.get("topic"),
                    description=card.get("description"),
                )
                relational_created += 1
            vector_cards.append({
                **card,
                "url": url,
                "knowledge_id": resource_id,
            })

        await db.flush()
        vector_indexed = 0
        if vector_cards:
            try:
                vector_indexed = await VectorKnowledgeRepo.upsert_resources(vector_cards)
            except Exception:
                logger.exception(
                    "Resource vector indexing failed: unique=%d, relational_created=%d, vector_failed=%d",
                    len(vector_cards),
                    relational_created,
                    len(vector_cards),
                )
        return KnowledgeIngestionResult(
            unique_count=len(vector_cards),
            relational_created=relational_created,
            vector_indexed=vector_indexed,
        )

    @staticmethod
    async def reindex_questions(db: AsyncSession) -> KnowledgeIngestionResult:
        """以关系库为数据源，重建/补偿全部面试题的 Chroma 索引。"""
        rows = await KnowledgeRepo.list_all_questions(db)
        cards = [
            {
                "knowledge_id": row.id,
                "question": row.question,
                "category": row.category,
                "difficulty": row.difficulty,
                "topic": row.topic,
                "expected_points": row.expected_points or [],
            }
            for row in rows
        ]
        indexed = await VectorKnowledgeRepo.upsert_questions(cards)
        return KnowledgeIngestionResult(
            unique_count=len(cards),
            relational_created=0,
            vector_indexed=indexed,
        )

    @staticmethod
    async def reindex_resources(db: AsyncSession) -> KnowledgeIngestionResult:
        """以关系库为数据源，重建/补偿全部学习资料的 Chroma 索引。"""
        rows = await KnowledgeRepo.list_all_resources(db)
        cards = [
            {
                "knowledge_id": row.id,
                "name": row.name,
                "type": row.type,
                "url": row.url,
                "topic": row.topic,
                "description": row.description,
            }
            for row in rows
        ]
        indexed = await VectorKnowledgeRepo.upsert_resources(cards)
        return KnowledgeIngestionResult(
            unique_count=len(cards),
            relational_created=0,
            vector_indexed=indexed,
        )
