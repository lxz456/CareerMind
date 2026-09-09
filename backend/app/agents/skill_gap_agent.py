# CareerMind AI Skill Gap Analysis Agent
import logging

from app.agents.state import CareerPlanningState
from app.llm.skill_gap import analyze_skill_gap

logger = logging.getLogger(__name__)

async def skill_gap_analysis_node(state: CareerPlanningState) -> dict:
    """Analyze resume skills against the combined requirements of all fetched jobs."""
    branch_errors = [
        error for error in (state.get("resume_error"), state.get("job_search_error"))
        if error
    ]
    if branch_errors:
        return {"error_message": "; ".join(branch_errors)}

    resume_data = state.get("resume_data", {}) or {}
    job_results = state.get("job_results") or []

    user_skills = resume_data.get("skills", [])
    user_skill_levels = resume_data.get("skill_levels", {})

    # Aggregate requirements from all 3-5 real listings instead of selecting only one.
    job_requirements = []
    seen_requirements = set()
    for job in job_results:
        title = job.get("title", "")
        company = job.get("company", "")
        for requirement in job.get("requirements", []) or []:
            text = str(requirement).strip()
            key = text.casefold()
            if text and key not in seen_requirements:
                seen_requirements.add(key)
                job_requirements.append(
                    f"[{title} @ {company}] {text}" if title or company else text
                )

    job_title = f"{state.get('target_position', '')}（综合 {len(job_results)} 个真实岗位）"

    if not job_requirements:
        return {
            "error_message": "真实岗位未提供可用于分析的职位要求，请稍后重试岗位搜索",
        }

    try:
        result = await analyze_skill_gap(
            user_skills=user_skills,
            skill_levels=user_skill_levels,
            job_title=job_title,
            job_requirements=job_requirements,
        )

        if not result.get("required_skills"):
            raise ValueError("技能差距模型未返回目标岗位所需技能")

        return {
            "skill_gap_data": result,
            "completed_steps": ["skill_gap"],
            "error_message": None,
        }
    except Exception as e:
        logger.exception("Skill gap analysis node failed")
        return {
            "error_message": f"Skill gap analysis failed: {str(e)}",
        }
