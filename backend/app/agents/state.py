# CareerMind AI Agent State Definitions
"""
Two independent paths, each with its own state:

  Path A — 规划提升: resume → job → skill_gap → career_plan
  Path B — 模拟面试: hr / technical / system_design / mixed
"""
import operator
from typing import TypedDict, Annotated, Optional
from langgraph.graph.message import add_messages


# ============================================================
# Path A: 规划提升 (Career Planning Pipeline)
# ============================================================

class CareerPlanningState(TypedDict):
    """State for the resume → job → gap → plan pipeline."""
    messages: Annotated[list, add_messages]

    # User context
    user_id: str
    resume_id: Optional[str]

    # Step 1: Resume
    resume_text: Optional[str]
    resume_data: Optional[dict]

    # Step 2: Job Search
    target_position: Optional[str]
    job_requirements: Optional[str]
    target_location: Optional[str]
    job_results: Optional[list]

    # Step 3: Skill Gap
    skill_gap_data: Optional[dict]

    # Step 4: Career Plan
    career_plan_data: Optional[dict]
    # 新采集资源由 WorkflowService 在数据库事务中统一双写。
    knowledge_resources: Optional[list[dict]]

    # Flow control
    current_step: str
    # Parallel nodes append their own step name; the reducer merges both branches.
    completed_steps: Annotated[list[str], operator.add]
    resume_error: Optional[str]
    job_search_error: Optional[str]
    error_message: Optional[str]

    # Final output
    final_summary: Optional[str]


def create_career_planning_state(
    user_id: str,
    resume_id: str = "",
    resume_text: str = "",
    target_position: str = "",
    job_requirements: str = "",
    target_location: str = "",
) -> CareerPlanningState:
    """Initial state for the career planning pipeline."""
    return CareerPlanningState(
        messages=[],
        user_id=user_id,
        resume_id=resume_id or None,
        resume_text=resume_text or None,
        resume_data=None,
        target_position=target_position or None,
        job_requirements=job_requirements or None,
        target_location=target_location or None,
        job_results=None,
        skill_gap_data=None,
        career_plan_data=None,
        knowledge_resources=None,
        current_step="resume_analysis",
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
    messages: Annotated[list, add_messages]

    # Session
    user_id: str
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

    # Answers & feedback
    answers: Annotated[list[dict], operator.add]
    feedbacks: Annotated[list[dict], operator.add]
    pending_answer: Optional[str]

    # LLM decision and hard guardrails
    next_action: Optional[str]  # follow_up | next_question | finish
    suggested_follow_up: Optional[str]
    answered_count: int
    max_follow_ups_per_question: int

    # Status
    status: str               # initializing | waiting_answer | evaluating | completed | failed
    result: Optional[dict]    # final summary after completion
    error_message: Optional[str]


def create_interview_state(
    *,
    user_id: str,
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
        messages=[],
        user_id=user_id,
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
        answers=[],
        feedbacks=[],
        pending_answer=None,
        next_action=None,
        suggested_follow_up=None,
        answered_count=0,
        max_follow_ups_per_question=1,
        status="initializing",
        result=None,
        error_message=None,
    )
