# CareerMind AI 向量数据库封装（ChromaDB）
#
# 管理两个知识集合：
#   interview_questions  面试题库
#   learning_resources   学习资源库
#
# 岗位数据走实时 JSearch，不存入向量库。
# 每个集合存：documents（文本）、metadatas（结构化字段）、embeddings（向量）。
# 检索时用语义向量匹配，返回 Top-K 相似条目。
from typing import Optional
import chromadb
from chromadb.config import Settings

from app.config import get_settings

settings = get_settings()

COLLECTION_QUESTIONS = "interview_questions"
COLLECTION_RESOURCES = "learning_resources"

# 两个集合的集合名 → 用途说明
COLLECTIONS = {
    COLLECTION_QUESTIONS: "面试题库",
    COLLECTION_RESOURCES: "学习资源库",
}


class VectorStore:
    """ChromaDB 封装：语义检索的知识库。"""

    def __init__(self):
        self._client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collections = {
            name: self._client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )
            for name in COLLECTIONS
        }

    # ---------------- 写入 ----------------

    def upsert(
        self,
        collection: str,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict] | None = None,
    ) -> None:
        """新增或更新条目。ids 作为唯一键，重复则覆盖。"""
        from app.llm.embedding import embed_texts
        col = self._get(collection)
        embeddings = embed_texts(documents)
        col.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas or [{}] * len(ids),
            embeddings=embeddings,
        )

    def delete(self, collection: str, ids: list[str]) -> None:
        """按 id 删除条目。"""
        if not ids:
            return
        col = self._get(collection)
        col.delete(ids=ids)

    def clear(self, collection: str) -> None:
        """清空整个集合（删除重建）。"""
        if collection not in self._collections:
            return
        try:
            self._client.delete_collection(collection)
        except Exception:
            pass
        self._collections[collection] = self._client.create_collection(
            name=collection,
            metadata={"hnsw:space": "cosine"},
        )

    # ---------------- 检索 ----------------

    def search(
        self,
        collection: str,
        query: str,
        top_k: int = 5,
        where: Optional[dict] = None,
    ) -> list[dict]:
        """语义检索 Top-K 条目。

        where: 可选过滤条件，如 {"category": "technical"}
        返回: [{"id", "document", "metadata", "score"}, ...] 按相似度降序
        """
        from app.llm.embedding import embed_query
        col = self._get(collection)
        q_vec = embed_query(query)
        result = col.query(
            query_embeddings=[q_vec],
            n_results=top_k,
            where=where,
        )

        items = []
        ids = result.get("ids", [[]])[0]
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        dists = result.get("distances", [[]])[0]

        for i, doc_id in enumerate(ids):
            items.append({
                "id": doc_id,
                "document": docs[i] if i < len(docs) else "",
                "metadata": metas[i] if i < len(metas) else {},
                "score": 1.0 - (dists[i] if i < len(dists) else 0.0),
            })
        return items

    def count(self, collection: str) -> int:
        """集合中的条目数。"""
        col = self._get(collection)
        return col.count()

    # ---------------- 内部 ----------------

    def _get(self, collection: str):
        if collection not in self._collections:
            raise ValueError(
                f"Unknown collection '{collection}'. Available: {list(COLLECTIONS)}"
            )
        return self._collections[collection]


# 全局单例，供各模块复用
_vector_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    """Get or create the shared VectorStore instance."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
