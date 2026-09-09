# CareerMind AI Career Planner Agent
import asyncio
import logging
import time

from app.agents.state import CareerPlanningState
from app.config import get_settings
from app.llm.career_plan import generate_career_plan
from app.tools.learning_resources import fetch_resources_for_topic

logger = logging.getLogger(__name__)


async def _enrich_plan_resources(result: dict) -> list[dict]:
    """以有限并发补充任务资源，并返回需要由 Service 双写的资源。"""
    task_topics: list[tuple[dict, str]] = []
    for month in result.get("plan", []):
        for task in month.get("tasks", []):
            topic = task.get("title", "") or task.get("description", "")
            if topic:
                task_topics.append((task, topic))

    if not task_topics:
        return []

    concurrency = max(1, get_settings().LEARNING_RESOURCE_CONCURRENCY)
    semaphore = asyncio.Semaphore(concurrency)

    async def fetch_one(task: dict, topic: str) -> tuple[dict, list[dict]]:
        async with semaphore:
            return task, await fetch_resources_for_topic(topic, top_k=2)

    started = time.perf_counter()
    enriched = await asyncio.gather(
        *(fetch_one(task, topic) for task, topic in task_topics)
    )

    resources_to_persist: list[dict] = []
    for task, items in enriched:
        if not items:
            continue
        resources_to_persist.extend(items)
        task["resources"] = [
            {
                "name": item.get("name", ""),
                "type": item.get("type", ""),
                "url": item.get("url", ""),
            }
            for item in items
        ]

    logger.info(
        "Plan resource enrichment completed tasks=%d resources=%d concurrency=%d duration_ms=%d",
        len(task_topics),
        len(resources_to_persist),
        concurrency,
        round((time.perf_counter() - started) * 1000),
    )
    return resources_to_persist

async def career_plan_node(state: CareerPlanningState) -> dict:
    """LangGraph node: generate career development plan."""
    skill_gap_data = state.get("skill_gap_data", {}) or {}
    target_position = state.get("target_position", "")

    if not skill_gap_data:
        return {
            "error_message": "No skill gap data available",
        }

    gaps = skill_gap_data.get("gaps", [])
    match_pct = skill_gap_data.get("match_percentage", 0)

    try:
        result = await generate_career_plan(
            target_position=target_position,
            match_pct=match_pct,
            gaps=gaps,
        )
        resources_to_persist = await _enrich_plan_resources(result)

        return {
            "career_plan_data": result,
            "knowledge_resources": resources_to_persist,
            "completed_steps": ["career_plan"],
            "error_message": None,
        }
    except Exception as e:
        logger.exception("Career plan node failed target_position=%s", target_position)
        return {
            "error_message": f"Career plan generation failed: {str(e)}",
        }
