"""面试题和学习资料的关系数据库访问。"""
import re
import unicodedata

import jieba
from sqlalchemy import or_, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import InterviewQuestion, LearningResource


_QUERY_STOP_WORDS = {
    "如何",
    "怎么",
    "怎样",
    "请问",
    "帮我",
    "给我",
    "一下",
    "关于",
    "有关",
    "想要",
    "请",
    "我",
    "想",
    "的",
    "了",
    "吗",
    "呢",
    "和",
    "与",
    "及",
    "以及",
}
_SEARCH_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]+|[a-z0-9][a-z0-9+#.\-]*")


def _normalize_search_query(query: str) -> str:
    """统一全/半角、英文大小写和空白，不改变向量检索使用的原始查询。"""
    normalized = unicodedata.normalize("NFKC", query or "").lower()
    return " ".join(normalized.split())


def _extract_search_terms(query: str) -> list[str]:
    """用 Jieba 搜索模式提取 BM25/LIKE 共用的中文与技术关键词。"""
    normalized = _normalize_search_query(query)
    terms: list[str] = []
    seen: set[str] = set()

    for segment in jieba.lcut_for_search(normalized):
        for token in _SEARCH_TOKEN_RE.findall(segment):
            token = token.strip(".-")
            if not token or token in _QUERY_STOP_WORDS:
                continue
            # 单个汉字噪声较大，并且无法被 trigram 索引有效召回。
            if len(token) == 1 and "\u4e00" <= token <= "\u9fff":
                continue
            if token not in seen:
                seen.add(token)
                terms.append(token)

    # 避免纯停用词查询完全失效，至少保留规范化后的原始输入用于 LIKE。
    return terms or ([normalized] if normalized else [])


def _fts_match_query(terms: list[str]) -> str:
    """为 trigram FTS5 构造安全 OR 查询；短于 3 字符的词交给 LIKE。"""
    searchable_terms = [term for term in terms if len(term.replace(" ", "")) >= 3]
    escaped_terms = [term.replace('"', '""') for term in searchable_terms]
    return " OR ".join(f'"{term}"' for term in escaped_terms)


def _like_any(columns: tuple, terms: list[str]):
    """构造按分词结果匹配任一字段、任一关键词的 LIKE 补充条件。"""
    return or_(*(column.ilike(f"%{term}%") for column in columns for term in terms))


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
        search_terms = _extract_search_terms(query)
        match_query = _fts_match_query(search_terms)
        hits: list[dict] = []
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
                if len(hits) >= limit:
                    return hits
            except OperationalError:
                # FTS5 不可用或旧环境尚未初始化时保留 LIKE 降级。
                pass

        # trigram 无法匹配 1～2 字符的词；FTS 结果不足时也用分词后的
        # 关键词补齐，而不是用整句做 LIKE，提升无空格中文查询的召回率。
        statement = select(InterviewQuestion)
        if category:
            statement = statement.where(InterviewQuestion.category == category)
        if difficulty:
            statement = statement.where(InterviewQuestion.difficulty == difficulty)
        existing_ids = [hit["item"].id for hit in hits]
        if existing_ids:
            statement = statement.where(InterviewQuestion.id.not_in(existing_ids))
        statement = statement.where(
            _like_any(
                (InterviewQuestion.question, InterviewQuestion.topic),
                search_terms,
            )
        ).limit(max(0, limit - len(hits)))
        result = await db.execute(statement)
        like_hits = [
            {"item": item, "bm25_score": float(len(hits) + index)}
            for index, item in enumerate(result.scalars().all())
        ]
        return hits + like_hits

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
        search_terms = _extract_search_terms(query)
        match_query = _fts_match_query(search_terms)
        hits: list[dict] = []
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
                if len(hits) >= limit:
                    return hits
            except OperationalError:
                pass

        statement = select(LearningResource)
        if item_type:
            statement = statement.where(LearningResource.type == item_type)
        existing_ids = [hit["item"].id for hit in hits]
        if existing_ids:
            statement = statement.where(LearningResource.id.not_in(existing_ids))
        statement = statement.where(
            _like_any(
                (
                    LearningResource.name,
                    LearningResource.topic,
                    LearningResource.description,
                ),
                search_terms,
            )
        ).limit(max(0, limit - len(hits)))
        result = await db.execute(statement)
        like_hits = [
            {"item": item, "bm25_score": float(len(hits) + index)}
            for index, item in enumerate(result.scalars().all())
        ]
        return hits + like_hits
