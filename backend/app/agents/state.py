# CareerMind AI Agent State Definitions
"""
Two independent paths, each with its own state:

  Path A — 规划提升: (resume_analysis || job_search) → skill_gap → career_plan → summary
  Path B — 模拟面试: hr / technical / system_design / mixed
"""
import operator
from typing import TypedDict, Annotated, Optional


# ============================================================
# Path A: 规划提升 (Career Planning Pipeline)
# ============================================================

class CareerPlanningState(TypedDict):
    """State for the parallel resume/job → gap → plan → summary pipeline."""

    # Parallel branch A: Resume analysis
    resume_text: Optional[str]
    resume_data: Optional[dict]

    # Parallel branch B: Job search
    target_position: Optional[str]
    target_location: Optional[str]
    job_results: Optional[list]

    # After join: Skill gap
    skill_gap_data: Optional[dict]

    # Career plan and collected resources
    career_plan_data: Optional[dict]
    # 新采集资源由 WorkflowService 在数据库事务中统一双写。
    knowledge_resources: Optional[list[dict]]

    # Flow control
    # Parallel nodes append their own step name; the reducer merges both branches.
    completed_steps: Annotated[list[str], operator.add]
    resume_error: Optional[str]
    job_search_error: Optional[str]
    error_message: Optional[str]

    # Final output
    final_summary: Optional[str]


def create_career_planning_state(
    resume_text: str = "",
    target_position: str = "",
    target_location: str = "",
) -> CareerPlanningState:
    """Initial state for the career planning pipeline."""
    return CareerPlanningState(
        resume_text=resume_text or None,
        resume_data=None,
        target_position=target_position or None,
        target_location=target_location or None,
        job_results=None,
        skill_gap_data=None,
        career_plan_data=None,
        knowledge_resources=None,
        completed_steps=[],
        resume_error=None,
        job_search_error=None,
        error_message=None,
        final_summary=None,
    )


# ============================================================
# Path B: 模拟面试 (Interview)
# ============================================================

class InterviewState(TypedDict):
    """State for the interruptible mock-interview graph."""

    # Session
    session_id: str
    interview_type: str       # hr | technical | system_design | mixed
    target_position: str
    difficulty: str
    question_mode: str       # review | advanced

    # Questions
    questions: list[dict]     # [{question_id, question, category, difficulty}]
    current_index: int
    total_questions: int
    current_question: Optional[dict]
    is_follow_up: bool
    follow_up_count: int

    # Feedback（其中已经包含题目和回答）
    feedbacks: Annotated[list[dict], operator.add]
    pending_answer: Optional[str]

    # LLM decision and hard guardrails
    next_action: Optional[str]  # follow_up | next_question | finish
    suggested_follow_up: Optional[str]
    max_follow_ups_per_question: int

    # Status
    status: str               # initializing | waiting_answer | evaluating | completed
    result: Optional[dict]    # final summary after completion


def create_interview_state(
    *,
    session_id: str,
    interview_type: str,
    target_position: str,
    question_mode: str = "review",
    difficulty: str = "medium",
    total_questions: int = 5,
) -> InterviewState:
    """创建路径 B 的完整初始状态。

    所有列表、可选字段和流程控制字段都在这里集中初始化，
    避免 API/Service 入口在启动 LangGraph 时遗漏 `InterviewState` 字段。
    """
    return InterviewState(
        session_id=session_id,
        interview_type=interview_type,
        target_position=target_position,
        question_mode=question_mode,
        difficulty=difficulty,
        total_questions=total_questions,
        questions=[],
        current_index=0,
        current_question=None,
        is_follow_up=False,
        follow_up_count=0,
        feedbacks=[],
        pending_answer=None,
        next_action=None,
        suggested_follow_up=None,
        max_follow_ups_per_question=1,
        status="initializing",
        result=None,
    )
