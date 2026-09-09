"""面试题和学习资料的关系数据库访问。"""
from sqlalchemy import or_, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import InterviewQuestion, LearningResource


def _fts_match_query(query: str) -> str:
    """把用户输入转成安全的 FTS5 OR 短语查询。"""
    terms = [part.replace('"', '""') for part in query.split() if part]
    return " OR ".join(f'"{term}"' for term in terms)


def _ordered_items(ids: list[str], objects: list) -> list:
    by_id = {obj.id: obj for obj in objects}
    return [by_id[item_id] for item_id in ids if item_id in by_id]


class KnowledgeRepo:
    """封装知识业务表 CRUD 与 SQLite FTS5 BM25 召回。"""

    @staticmethod
    async def get_question_by_id(
        db: AsyncSession, question_id: str
    ) -> InterviewQuestion | None:
        return await db.get(InterviewQuestion, question_id)

    @staticmethod
    async def get_questions_by_ids(
        db: AsyncSession, ids: list[str]
    ) -> list[InterviewQuestion]:
        if not ids:
            return []
        result = await db.execute(
            select(InterviewQuestion).where(InterviewQuestion.id.in_(ids))
        )
        return _ordered_items(ids, list(result.scalars().all()))

    @staticmethod
    async def list_all_questions(db: AsyncSession) -> list[InterviewQuestion]:
        """返回全部面试题，供向量索引修复等维护用例使用。"""
        result = await db.execute(select(InterviewQuestion))
        return list(result.scalars().all())

    @staticmethod
    async def create_question(
        db: AsyncSession,
        *,
        id: str,
        question: str,
        category: str | None,
        difficulty: str | None,
        topic: str | None,
        expected_points: list | None,
    ) -> InterviewQuestion:
        obj = InterviewQuestion(
            id=id,
            question=question,
            category=category,
            difficulty=difficulty,
            topic=topic,
            expected_points=expected_points or [],
        )
        db.add(obj)
        return obj

    @staticmethod
    async def search_questions_bm25(
        db: AsyncSession,
        *,
        query: str,
        category: str | None,
        difficulty: str | None,
        limit: int,
    ) -> list[dict]:
        """返回按 BM25 从优到劣排序的题目及原始 BM25 分值。"""
        match_query = _fts_match_query(query)
        if match_query:
            try:
                result = await db.execute(
                    text(
                        """SELECT id,
                                  bm25(interview_questions_fts, 0.0, 5.0, 2.0, 0.0, 0.0)
                                      AS bm25_score
                           FROM interview_questions_fts
                           WHERE interview_questions_fts MATCH :query
                             AND (:category IS NULL OR category = :category)
                             AND (:difficulty IS NULL OR difficulty = :difficulty)
                           ORDER BY bm25_score
                           LIMIT :limit"""
                    ),
                    {
                        "query": match_query,
                        "category": category,
                        "difficulty": difficulty,
                        "limit": limit,
                    },
                )
                ranks = list(result.mappings())
                objects = await KnowledgeRepo.get_questions_by_ids(
                    db, [row["id"] for row in ranks]
                )
                by_id = {obj.id: obj for obj in objects}
                hits = [
                    {"item": by_id[row["id"]], "bm25_score": row["bm25_score"]}
                    for row in ranks
                    if row["id"] in by_id
                ]
                if hits:
                    return hits
            except OperationalError:
                # FTS5 不可用或旧环境尚未初始化时保留 LIKE 降级。
                pass

        statement = select(InterviewQuestion)
        if category:
            statement = statement.where(InterviewQuestion.category == category)
        if difficulty:
            statement = statement.where(InterviewQuestion.difficulty == difficulty)
        statement = statement.where(
            or_(
                InterviewQuestion.question.ilike(f"%{query}%"),
                InterviewQuestion.topic.ilike(f"%{query}%"),
            )
        ).limit(limit)
        result = await db.execute(statement)
        return [
            {"item": item, "bm25_score": float(index)}
            for index, item in enumerate(result.scalars().all())
        ]

    @staticmethod
    async def get_resource_by_id(
        db: AsyncSession, resource_id: str
    ) -> LearningResource | None:
        return await db.get(LearningResource, resource_id)

    @staticmethod
    async def get_resource_by_url(
        db: AsyncSession, url: str
    ) -> LearningResource | None:
        """按真实资源 URL 查重；同一链接即视为同一学习资料。"""
        if not url:
            return None
        result = await db.execute(
            select(LearningResource).where(LearningResource.url == url).limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_resources_by_ids(
        db: AsyncSession, ids: list[str]
    ) -> list[LearningResource]:
        if not ids:
            return []
        result = await db.execute(
            select(LearningResource).where(LearningResource.id.in_(ids))
        )
        return _ordered_items(ids, list(result.scalars().all()))

    @staticmethod
    async def list_all_resources(db: AsyncSession) -> list[LearningResource]:
        """返回全部学习资料，供向量索引修复等维护用例使用。"""
        result = await db.execute(select(LearningResource))
        return list(result.scalars().all())

    @staticmethod
    async def create_resource(
        db: AsyncSession,
        *,
        id: str,
        name: str,
        type: str | None,
        url: str | None,
        topic: str | None,
        description: str | None,
    ) -> LearningResource:
        obj = LearningResource(
            id=id,
            name=name,
            type=type,
            url=url,
            topic=topic,
            description=description,
        )
        db.add(obj)
        return obj

    @staticmethod
    async def search_resources_bm25(
        db: AsyncSession,
        *,
        query: str,
        item_type: str | None,
        limit: int,
    ) -> list[dict]:
        """返回按 BM25 从优到劣排序的资源及原始 BM25 分值。"""
        match_query = _fts_match_query(query)
        if match_query:
            try:
                result = await db.execute(
                    text(
                        """SELECT id,
                                  bm25(learning_resources_fts, 0.0, 5.0, 2.0, 1.0, 0.0, 0.0)
                                      AS bm25_score
                           FROM learning_resources_fts
                           WHERE learning_resources_fts MATCH :query
                             AND (:item_type IS NULL OR "type" = :item_type)
                           ORDER BY bm25_score
                           LIMIT :limit"""
                    ),
                    {
                        "query": match_query,
                        "item_type": item_type,
                        "limit": limit,
                    },
                )
                ranks = list(result.mappings())
                objects = await KnowledgeRepo.get_resources_by_ids(
                    db, [row["id"] for row in ranks]
                )
                by_id = {obj.id: obj for obj in objects}
                hits = [
                    {"item": by_id[row["id"]], "bm25_score": row["bm25_score"]}
                    for row in ranks
                    if row["id"] in by_id
                ]
                if hits:
                    return hits
            except OperationalError:
                pass

        statement = select(LearningResource)
        if item_type:
            statement = statement.where(LearningResource.type == item_type)
        statement = statement.where(
            or_(
                LearningResource.name.ilike(f"%{query}%"),
                LearningResource.topic.ilike(f"%{query}%"),
                LearningResource.description.ilike(f"%{query}%"),
            )
        ).limit(limit)
        result = await db.execute(statement)
        return [
            {"item": item, "bm25_score": float(index)}
            for index, item in enumerate(result.scalars().all())
        ]
