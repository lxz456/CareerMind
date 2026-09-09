# CareerMind AI Embedding 封装
#
# 使用千问 text-embedding-v3，通过 OpenAI 兼容接口（DashScope）调用。
# 供向量库（vector_store.py）做文本向量化。
import logging
import time

from openai import OpenAI

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

def _get_embedding_client() -> OpenAI:
    """Get the DashScope OpenAI-compatible embedding client."""
    return OpenAI(
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.DASHSCOPE_BASE_URL,
        timeout=settings.EMBEDDING_TIMEOUT_SECONDS,
        max_retries=settings.EMBEDDING_MAX_RETRIES,
    )


def _get_embedding_model() -> str:
    """从环境配置解析 DashScope Embedding 模型名。"""
    return settings.EMBEDDING_MODEL


def embed_texts(texts: list[str]) -> list[list[float]]:
    """按服务端允许的批量大小生成向量，并保持与输入相同的顺序。

    DashScope ``text-embedding-v3`` 单次最多接收 10 条文本。调用方可能一次
    写入几十条知识数据，因此在本层统一分批，所有向量写入路径都会生效。
    """
    if not texts:
        return []

    started = time.perf_counter()
    client = _get_embedding_client()
    model = _get_embedding_model()
    configured_batch_size = max(1, settings.EMBEDDING_BATCH_SIZE)
    batch_size = min(configured_batch_size, 10)

    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        response = client.embeddings.create(model=model, input=batch)
        batch_vectors: list[list[float] | None] = [None] * len(batch)
        for item in response.data:
            if 0 <= item.index < len(batch_vectors):
                batch_vectors[item.index] = item.embedding

        if any(vector is None for vector in batch_vectors):
            raise RuntimeError(
                f"Embedding response is incomplete for batch starting at {start}"
            )
        vectors.extend(vector for vector in batch_vectors if vector is not None)

    logger.info(
        "Embedding completed model=%s texts=%d batches=%d duration_ms=%d",
        model,
        len(texts),
        (len(texts) + batch_size - 1) // batch_size,
        round((time.perf_counter() - started) * 1000),
    )
    return vectors


def embed_query(text: str) -> list[float]:
    """Embed a single query string."""
    result = embed_texts([text])
    return result[0] if result else []
