"""JSearch external-data tool.

This module owns market localization, HTTP transport, response validation, and
normalization. Business workflows consume normalized candidate cards and do
not depend on the provider's response shape.
"""
import asyncio
import logging
import re
import time

import httpx

from app.config import get_settings
from app.llm.job_search import normalize_job_search_query, rank_jobs
from app.utils.retry import retry_http_call


JSEARCH_MARKETS = {
    "us": {
        "query_location": "United States", "country": "us", "language": "en"
    },
    "gb": {
        "query_location": "United Kingdom", "country": "gb", "language": "en"
    },
    "de": {
        "query_location": "Germany", "country": "de", "language": "de"
    },
    "jp": {
        "query_location": "Japan", "country": "jp", "language": "ja"
    },
    "sg": {
        "query_location": "Singapore", "country": "sg", "language": "en"
    },
    "hk": {
        "query_location": "Hong Kong", "country": "hk", "language": "zh"
    },
    "tw": {
        "query_location": "Taiwan", "country": "tw", "language": "zh"
    },
}
logger = logging.getLogger(__name__)


def market_name(market_code: str | None) -> str:
    """Return the provider-facing location name for a market code or free text."""
    value = (market_code or "").strip()
    market = JSEARCH_MARKETS.get(value.lower())
    return market["query_location"] if market else value


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _extract_job_requirements(job: dict, description: str) -> list[str]:
    """优先读取结构化要求；缺失时提取职位描述中的要求段落。"""
    highlights = job.get("job_highlights") or {}
    structured = []
    for label, values in highlights.items():
        normalized_label = str(label).casefold()
        if "qualification" not in normalized_label and "requirement" not in normalized_label:
            continue
        if isinstance(values, list):
            structured.extend(str(value).strip() for value in values if str(value).strip())
        elif str(values or "").strip():
            structured.append(str(values).strip())
    if structured:
        return structured

    if not description:
        return []

    lowered = description.casefold()
    start_markers = (
        "candidate requirements",
        "job requirements",
        "minimum requirements",
        "requirements",
        "qualifications",
        "what you bring",
        "required skills",
    )
    # 标记按具体程度排序，避免把正文里的普通短语（如 business requirements）
    # 误认为真正的 Candidate Requirements 标题。
    start = 0
    for marker in start_markers:
        position = lowered.find(marker)
        if position >= 0:
            start = position
            break

    section = description[start:]
    lowered_section = section.casefold()
    end_markers = (
        "benefits",
        "what we offer",
        "compensation",
        "about the company",
        "about us",
        "equal opportunity",
    )
    ends = [lowered_section.find(marker, 80) for marker in end_markers]
    ends = [position for position in ends if position >= 0]
    if ends:
        section = section[:min(ends)]

    # 作为一段保留，由技能差距模型从真实原文中提取技能；限制长度避免提示词失控。
    requirement_text = section.strip()[:3500]
    return [requirement_text] if requirement_text else []


def normalize_job(job: dict) -> dict:
    """Normalize one provider job into CareerMind's stable job-card schema."""
    city = job.get("job_city") or ""
    country = job.get("job_country") or ""
    description = _strip_html(job.get("job_description") or "")
    return {
        "job_id": job.get("job_id") or "",
        "title": job.get("job_title") or "",
        "company": job.get("employer_name") or "",
        "location": ", ".join(part for part in (city, country) if part),
        "salary_range": job.get("job_salary") or "",
        "requirements": _extract_job_requirements(job, description),
        "description": description[:2000],
        "source_url": job.get("job_apply_link") or "",
    }


def _deduplicate_candidate_cards(cards: list[dict], limit: int) -> list[dict]:
    """按岗位 ID、来源链接和核心字段合并多语言检索结果。"""
    unique = []
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    seen_fields: set[tuple[str, str, str]] = set()
    for card in cards:
        job_id = str(card.get("job_id", "")).strip()
        source_url = str(card.get("source_url", "")).strip().casefold()
        fields = tuple(
            str(card.get(field, "")).strip().casefold()
            for field in ("title", "company", "location")
        )
        if not fields[0]:
            continue
        if (
            (job_id and job_id in seen_ids)
            or (source_url and source_url in seen_urls)
            or fields in seen_fields
        ):
            continue
        if job_id:
            seen_ids.add(job_id)
        if source_url:
            seen_urls.add(source_url)
        seen_fields.add(fields)
        unique.append(card)
        if len(unique) >= max(limit, 1):
            break
    return unique


async def fetch_job_candidates(
    target_position: str,
    market_code: str | None = None,
) -> list[dict]:
    """Fetch and normalize real JSearch jobs for a position and market."""
    settings = get_settings()
    if not settings.JSEARCH_API_KEY:
        raise ValueError("JSEARCH_API_KEY 未配置")

    code = (market_code or "").strip().lower()
    market = JSEARCH_MARKETS.get(code)
    location = market_name(market_code)
    # 用户可输入中文，但 JSearch 的国际岗位索引使用英文职位关键词更稳定。
    query = await normalize_job_search_query(target_position)
    if location:
        query = f"{query} in {location}"

    base_params = {
        "query": query,
        "num_pages": 1,
    }
    if market:
        base_params["country"] = market["country"]

    # 非英语市场同时召回当地语言和英文结果；英语市场只请求一次。
    local_language = market["language"] if market else "en"
    languages = list(dict.fromkeys((local_language, "en")))

    async with httpx.AsyncClient(
        timeout=settings.JSEARCH_TIMEOUT_SECONDS,
        verify=False,
    ) as client:
        async def request_jobs(request_params: dict) -> list[dict]:
            started = time.perf_counter()
            response = await client.get(
                f"https://{settings.JSEARCH_RAPIDAPI_HOST}/jsearch/search-v2",
                params=request_params,
                headers={"X-API-Key": settings.JSEARCH_API_KEY},
            )
            response.raise_for_status()
            jobs = (response.json().get("data") or {}).get("jobs", [])
            logger.info(
                "JSearch call completed language=%s status_code=%d duration_ms=%d results=%d",
                request_params["language"],
                response.status_code,
                round((time.perf_counter() - started) * 1000),
                len(jobs),
            )
            return jobs

        async def request_with_retry(request_params: dict) -> list[dict]:
            return await retry_http_call(
                lambda: request_jobs(request_params),
                service="jsearch",
                max_retries=settings.EXTERNAL_API_MAX_RETRIES,
                backoff_seconds=settings.EXTERNAL_API_RETRY_BACKOFF_SECONDS,
            )

        async def request_language(language: str) -> tuple[str, list[dict], Exception | None]:
            try:
                jobs = await request_with_retry({**base_params, "language": language})
                return language, jobs, None
            except Exception as exc:
                # 单路失败不应丢弃另一语言已经成功取得的真实岗位。
                return language, [], exc

        results = await asyncio.gather(*(request_language(language) for language in languages))

    raw_jobs = []
    errors: list[tuple[str, Exception]] = []
    successful_languages = []
    for language, jobs, error in results:
        if error is not None:
            errors.append((language, error))
            logger.warning(
                "JSearch language branch failed language=%s error_type=%s error=%s",
                language,
                type(error).__name__,
                error,
            )
            continue
        successful_languages.append(language)
        raw_jobs.extend(jobs)

    if not successful_languages:
        # 所有语言分支都失败时保持原有语义：向上抛出外部服务异常。
        raise errors[0][1]

    cards = _deduplicate_candidate_cards(
        [normalize_job(job) for job in raw_jobs],
        settings.JSEARCH_MAX_RESULTS,
    )
    logger.info(
        "JSearch candidates merged market=%s requested_languages=%s "
        "successful_languages=%s raw_results=%d unique_results=%d",
        code or "global",
        ",".join(languages),
        ",".join(successful_languages),
        len(raw_jobs),
        len(cards),
    )
    return [
        {
            "metadata": {
                "job_id": card["job_id"],
                "title": card["title"],
                "company": card["company"],
                "location": card["location"],
                "salary_range": card["salary_range"],
                "requirements": card["requirements"],
                "description": card["description"],
                "source_url": card["source_url"],
            },
            "document": "\n".join([
                card["title"],
                card["company"],
                card["location"],
                " ".join(str(item) for item in card["requirements"]),
                card["description"],
            ]),
        }
        for card in cards if card["title"]
    ]


def _deduplicate_jobs(jobs: list[dict], limit: int) -> list[dict]:
    """按标题、公司和地点去重，最多保留五个真实岗位。"""
    unique = []
    seen = set()
    for job in jobs:
        key = tuple(
            str(job.get(field, "")).strip().casefold()
            for field in ("title", "company", "location")
        )
        if not key[0] or key in seen:
            continue
        seen.add(key)
        unique.append(job)
        if len(unique) >= min(max(limit, 1), 5):
            break
    return unique


async def search_jobs(
    target_position: str,
    user_skills: list[str] | None = None,
    location: str | None = None,
    top_k: int = 5,
) -> dict:
    """实时获取真实岗位，再调用 LLM 排序并去重。

    Provider 请求异常会继续向上抛出，由 Agent 标记为“搜索失败”；只有接口正常返回
    空列表时才表示确实没有匹配岗位。
    """
    candidates = await fetch_job_candidates(
        target_position,
        market_code=location,
    )
    if not candidates:
        return {"jobs": []}

    ranked = await rank_jobs(
        candidates=candidates,
        target_position=target_position,
        user_skills=user_skills or [],
        location_label=market_name(location),
        top_k=top_k,
    )
    jobs = _deduplicate_jobs(ranked.get("jobs", []), top_k)
    logger.info(
        "Job search completed target=%s market=%s candidates=%d ranked=%d returned=%d",
        target_position,
        location or "global",
        len(candidates),
        len(ranked.get("jobs", [])),
        len(jobs),
    )
    return {"jobs": jobs}
