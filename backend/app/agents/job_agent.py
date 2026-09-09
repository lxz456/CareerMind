# CareerMind AI Job Search Agent
import logging

from app.agents.state import CareerPlanningState
from app.tools.jsearch import search_jobs

logger = logging.getLogger(__name__)

async def job_search_node(state: CareerPlanningState) -> dict:
    """Search real jobs from the required UI target, independently of resume parsing."""
    target_position = state.get("target_position", "")

    if not target_position:
        return {
            "completed_steps": ["job_search"],
            "job_search_error": "No target position specified",
        }

    try:
        result = await search_jobs(
            target_position=target_position,
            # Resume analysis runs in parallel. Skill matching belongs to skill_gap.
            user_skills=[],
            location=state.get("target_location"),
            job_requirements=state.get("job_requirements"),
            top_k=5,
        )

        jobs = result.get("jobs", [])

        return {
            "job_results": jobs,
            "completed_steps": ["job_search"],
            "job_search_error": None if jobs else "No matching jobs found",
        }
    except Exception as e:
        logger.exception("Job search node failed target_position=%s", target_position)
        return {
            "completed_steps": ["job_search"],
            "job_search_error": f"Job search failed: {str(e)}",
        }
