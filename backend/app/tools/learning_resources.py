"""学习资源的检索与外部采集工具。"""
import logging

from app.llm.content_cleaner import clean_learning_resources
from app.tools.tavily import tavily_search

logger = logging.getLogger(__name__)


async def collect_learning_resource_cards(
    query: str,
) -> list[dict]:
    """通过 Tavily 搜索并用 LLM 清洗资源，但不负责持久化。"""
    raw_results = await tavily_search(query)
    return await clean_learning_resources(raw_results)


async def fetch_resources_for_topic(
    topic: str,
    top_k: int = 3,
) -> list[dict]:
    """直接通过 Tavily 采集主题资料；不查询本地向量缓存。"""
    if not topic:
        return []

    try:
        cards = await collect_learning_resource_cards(topic)
        return [
            {
                "name": card.get("name", ""),
                "type": card.get("type", ""),
                "url": card.get("url", ""),
                "topic": card.get("topic", "") or topic,
                "description": card.get("description", ""),
            }
            for card in cards[:top_k]
            if card.get("url")
        ]
    except Exception as exc:
        # 资源增强属于可选能力，失败时由调用方保留 LLM 原始推荐。
        logger.warning("Learning-resource collection failed: %s", exc)
        return []
