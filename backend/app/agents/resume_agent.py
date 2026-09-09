# CareerMind AI Resume Analysis Agent
import logging

from app.agents.state import CareerPlanningState
from app.llm.resume_parser import parse_resume_text

logger = logging.getLogger(__name__)

async def resume_analysis_node(state: CareerPlanningState) -> dict:
    """LangGraph node: analyze resume and extract structured data."""
    resume_text = state.get("resume_text")
    if not resume_text:
        return {
            "completed_steps": ["resume_analysis"],
            "resume_error": "No resume text provided",
        }

    try:
        # Parse resume with LLM
        parsed = await parse_resume_text(resume_text)

        return {
            "resume_data": parsed,
            "completed_steps": ["resume_analysis"],
            "resume_error": None,
        }
    except Exception as e:
        logger.exception("Resume analysis node failed")
        return {
            "completed_steps": ["resume_analysis"],
            "resume_error": f"Resume analysis failed: {str(e)}",
        }
