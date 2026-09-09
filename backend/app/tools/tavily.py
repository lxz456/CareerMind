"""供学习资源采集复用的 Tavily Web 搜索适配器。"""
import logging
import time

import httpx

from app.config import get_settings
from app.utils.retry import retry_http_call

logger = logging.getLogger(__name__)


async def tavily_search(query: str) -> list[dict]:
    """Search Tavily and return a stable subset of its web-result fields."""
    settings = get_settings()
    if not settings.TAVILY_API_KEY:
        raise ValueError("TAVILY_API_KEY 未配置")

    async with httpx.AsyncClient(timeout=settings.TAVILY_TIMEOUT_SECONDS) as client:
        async def request():
            started = time.perf_counter()
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": settings.TAVILY_API_KEY,
                    "query": query,
                    "max_results": settings.TAVILY_MAX_RESULTS,
                    "search_depth": "basic",
                },
            )
            response.raise_for_status()
            data = response.json()
            logger.info(
                "Tavily call completed status_code=%d duration_ms=%d results=%d",
                response.status_code,
                round((time.perf_counter() - started) * 1000),
                len(data.get("results", [])),
            )
            return data

        data = await retry_http_call(
            request,
            service="tavily",
            max_retries=settings.EXTERNAL_API_MAX_RETRIES,
            backoff_seconds=settings.EXTERNAL_API_RETRY_BACKOFF_SECONDS,
        )

    return [
        {
            "title": item.get("title", ""),
            "content": item.get("content", ""),
            "url": item.get("url", ""),
            "score": item.get("score"),
        }
        for item in data.get("results", [])
    ]
