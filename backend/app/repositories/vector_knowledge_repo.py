"""面试题和学习资源的 ChromaDB 数据访问层。"""
import asyncio
import hashlib

from app.vector_store import (
    COLLECTION_QUESTIONS,
    COLLECTION_RESOURCES,
    get_vector_store,
)


class VectorKnowledgeRepo:
    """封装知识库的向量序列化、集合选择和 ChromaDB CRUD。"""

    @staticmethod
    def question_id(card: dict) -> str:
        """根据题目知识 ID 或内容生成稳定 ID，不使用会话内运行时 ID。"""
        return card.get("knowledge_id") or _stable_id(
            card.get("category", ""), card.get("question", "")
        )

    @staticmethod
    def resource_id(card: dict) -> str:
        """根据资源知识 ID 或内容生成稳定 ID。"""
        return card.get("knowledge_id") or _stable_id(
            card.get("name", ""), card.get("url", "")
        )

    @classmethod
    async def upsert_questions(cls, cards: list[dict]) -> int:
        """把结构化面试题写入向量集合，不阻塞 asyncio 事件循环。"""
        if not cards:
            return 0
        ids = [cls.question_id(card) for card in cards]
        documents = [
            "\n".join([
                card.get("question") or "",
                "考察点: " + ", ".join(
                    str(point) for point in (card.get("expected_points") or [])
                ),
            ])
            for card in cards
        ]
        metadatas = [
            {
                "question": card.get("question") or "",
                "category": card.get("category") or "general",
                "difficulty": card.get("difficulty") or "medium",
                "topic": card.get("topic") or "",
            }
            for card in cards
        ]
        await asyncio.to_thread(
            lambda: get_vector_store().upsert(
                COLLECTION_QUESTIONS, ids, documents, metadatas
            )
        )
        return len(ids)

    @classmethod
    async def upsert_resources(cls, cards: list[dict]) -> int:
        """把结构化学习资源写入向量集合，不阻塞 asyncio 事件循环。"""
        if not cards:
            return 0
        ids = [cls.resource_id(card) for card in cards]
        documents = [
            "\n".join([
                card.get("name") or "",
                card.get("topic") or "",
                card.get("description") or "",
            ])
            for card in cards
        ]
        metadatas = [
            {
                "name": card.get("name") or "",
                "type": card.get("type") or "",
                "url": card.get("url") or "",
                "topic": card.get("topic") or "",
                "description": card.get("description") or "",
            }
            for card in cards
        ]
        await asyncio.to_thread(
            lambda: get_vector_store().upsert(
                COLLECTION_RESOURCES, ids, documents, metadatas
            )
        )
        return len(ids)

    @staticmethod
    async def search_questions(
        query: str,
        *,
        top_k: int = 5,
        category: str | None = None,
        difficulty: str | None = None,
    ) -> list[dict]:
        """按语义查询面试题，并可按分类和难度过滤。"""
        filters = []
        if category:
            filters.append({"category": category})
        if difficulty:
            filters.append({"difficulty": difficulty})
        where = None
        if len(filters) == 1:
            where = filters[0]
        elif filters:
            where = {"$and": filters}
        return await asyncio.to_thread(
            lambda: get_vector_store().search(
                COLLECTION_QUESTIONS, query, top_k, where
            )
        )

    @staticmethod
    async def search_resources(
        query: str,
        *,
        top_k: int = 5,
        resource_type: str | None = None,
    ) -> list[dict]:
        """按语义查询学习资源，并可按资源类型过滤。"""
        where = {"type": resource_type} if resource_type else None
        return await asyncio.to_thread(
            lambda: get_vector_store().search(
                COLLECTION_RESOURCES, query, top_k, where
            )
        )

    @staticmethod
    async def delete_questions(ids: list[str]) -> None:
        """按 ID 删除面试题向量。"""
        await asyncio.to_thread(
            lambda: get_vector_store().delete(COLLECTION_QUESTIONS, ids)
        )

    @staticmethod
    async def delete_resources(ids: list[str]) -> None:
        """按 ID 删除学习资源向量。"""
        await asyncio.to_thread(
            lambda: get_vector_store().delete(COLLECTION_RESOURCES, ids)
        )


def _stable_id(*parts: str) -> str:
    """根据业务唯一内容生成可重复计算的向量条目 ID。"""
    seed = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]
