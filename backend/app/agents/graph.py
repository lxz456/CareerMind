# CareerMind AI LangGraph Definitions
"""
Two independent agent graphs:

  Path A — 规划提升: (resume_analysis || job_search) → skill_gap → career_plan → summary
  Path B — 模拟面试: standalone, managed by interview_service via checkpoint
"""
from typing import Optional
from langgraph.graph import StateGraph, START, END

from app.agents.state import CareerPlanningState, create_career_planning_state
from app.agents.resume_agent import resume_analysis_node
from app.agents.job_agent import job_search_node
from app.agents.skill_gap_agent import skill_gap_analysis_node
from app.agents.career_planner_agent import career_plan_node
from app.agents.supervisor import supervisor_summary_node
from app.config import get_settings
from app.memory.checkpoint import get_checkpointer


career_planning_graph = None


# ============================================================
# Path A: 规划提升 Graph
#   resume_analysis ─┐
#                    ├→ skill_gap → career_plan → summary
#   job_search ──────┘
# ============================================================

def build_career_planning_graph() -> StateGraph:
    """Build the career planning pipeline graph."""
    graph = StateGraph(CareerPlanningState)

    graph.add_node("resume_analysis", resume_analysis_node)
    graph.add_node("job_search", job_search_node)
    graph.add_node("skill_gap", skill_gap_analysis_node)
    graph.add_node("career_plan", career_plan_node)
    graph.add_node("summary", supervisor_summary_node)

    # Fan out: both nodes only read initial input and write branch-specific fields.
    graph.add_edge(START, "resume_analysis")
    graph.add_edge(START, "job_search")

    # Explicit join: skill_gap starts only after both parallel branches finish.
    graph.add_edge(["resume_analysis", "job_search"], "skill_gap")
    graph.add_conditional_edges(
        "skill_gap",
        _route_after_node,
        {"continue": "career_plan", "error": "summary"},
    )
    graph.add_conditional_edges(
        "career_plan",
        _route_after_node,
        {"continue": "summary", "error": "summary"},
    )
    graph.add_edge("summary", END)

    return graph


def _route_after_node(state: CareerPlanningState) -> str:
    """Route after each agent node: continue if no error, else skip to summary."""
    if state.get("error_message"):
        return "error"
    return "continue"


_PLAN_STEPS = ("resume_analysis", "job_search", "skill_gap", "career_plan", "summary")

def init_career_planning_graph():
    """Compile Path A after the application opens its SQLite checkpointer."""
    global career_planning_graph
    career_planning_graph = build_career_planning_graph().compile(
        checkpointer=get_checkpointer()
    )
    return career_planning_graph


def get_career_planning_graph():
    if career_planning_graph is None:
        raise RuntimeError("Career planning graph has not been initialized")
    return career_planning_graph


async def run_career_planning_pipeline(
    user_id: str,
    resume_text: str,
    target_position: str = "",
    resume_id: str = "",
    thread_id: Optional[str] = None,
    job_requirements: str = "",
    target_location: str = "",
    resume_from_checkpoint: bool = False,
    on_step=None,
) -> dict:
    """Run the career planning pipeline with checkpoint support.

    Path A: 简历分析与岗位搜索并行 → 技能差距 → 学习规划

    Args:
        user_id: User ID
        resume_text: Full text extracted from the uploaded resume
        target_position: Required job title supplied by the user
        resume_id: DB resume record ID for reference
        thread_id: Checkpoint thread ID. Same ID = resume from last saved state.
        job_requirements / target_location: JSearch 工作要求与地点筛选

    Returns:
        Final state with resume_data, job_results, skill_gap_data, career_plan_data
    """
    config = {
        "configurable": {"thread_id": thread_id or user_id},
        "recursion_limit": get_settings().AGENT_RECURSION_LIMIT,
    }

    graph_input = None
    if not resume_from_checkpoint:
        graph_input = create_career_planning_state(
            user_id=user_id,
            resume_id=resume_id,
            resume_text=resume_text,
            target_position=target_position,
            job_requirements=job_requirements,
            target_location=target_location,
        )

    # stream_mode=values emits the merged state after each graph superstep. The two
    # parallel branches therefore appear atomically once both have completed.
    graph = get_career_planning_graph()
    async for state in graph.astream(
        graph_input, config, stream_mode="values"
    ):
        if on_step is not None:
            completed = list(state.get("completed_steps") or [])
            current = _next_pending_step(completed)
            progress = round(len(completed) / len(_PLAN_STEPS) * 100, 1)
            await on_step(current, progress, completed)
    if "state" not in locals():
        snapshot = await graph.aget_state(config)
        return snapshot.values if snapshot else {}
    return state


def _next_pending_step(completed: list[str]) -> str:
    """Return a stable UI step name for the parallel five-node pipeline."""
    done = set(completed)
    if not {"resume_analysis", "job_search"}.issubset(done):
        return "parallel_analysis"
    for step in ("skill_gap", "career_plan", "summary"):
        if step not in done:
            return step
    return "summary"


async def get_checkpoint_state(thread_id: str) -> dict | None:
    """Query the current checkpoint state for a thread without advancing."""
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": get_settings().AGENT_RECURSION_LIMIT,
    }
    state = await get_career_planning_graph().aget_state(config)
    return state.values if state else None
