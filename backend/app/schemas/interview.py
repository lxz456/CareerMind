# CareerMind AI Interview Schemas
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Literal
from datetime import datetime

class InterviewStartRequest(BaseModel):
    interview_type: Literal["hr", "technical", "system_design", "mixed"]
    job_title: str = Field(..., min_length=1, max_length=100)
    question_mode: Literal["review", "advanced"] = "review"
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    question_count: int = Field(default=5, ge=1, le=20)

    @field_validator("job_title")
    @classmethod
    def validate_job_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("目标岗位不能为空")
        return value

class InterviewAnswerRequest(BaseModel):
    answer: str = Field(..., min_length=1, description="Candidate's answer")

    @field_validator("answer")
    @classmethod
    def validate_answer(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("回答不能为空")
        return value

class InterviewQuestion(BaseModel):
    question_id: str
    question_number: int
    question: str
    category: Optional[str] = None  # behavioral | technical | system_design | hr
    difficulty: Optional[str] = None
    is_follow_up: bool = False
    parent_question_id: Optional[str] = None

class InterviewFeedback(BaseModel):
    question_id: Optional[str] = None
    question_number: Optional[int] = None
    is_follow_up: bool = False
    parent_question_id: Optional[str] = None
    difficulty: Optional[str] = None
    question: str = ""
    answer: str = ""
    score: float = Field(ge=0, le=10)
    strengths: List[str] = Field(default_factory=list)
    improvements: List[str] = Field(default_factory=list)
    model_answer: Optional[str] = None
    comments: str = ""

class InterviewResult(BaseModel):
    total_score: float = 0.0
    feedbacks: List[InterviewFeedback] = Field(default_factory=list)
    overall_assessment: str = ""
    strengths: List[str] = Field(default_factory=list)
    areas_to_improve: List[str] = Field(default_factory=list)
    tips: List[str] = Field(default_factory=list)

class InterviewSessionResponse(BaseModel):
    session_id: str
    interview_type: str
    status: str  # in_progress / completed
    current_question: Optional[InterviewQuestion] = None
    current_question_index: int = 0
    total_questions: int = 0
    result: Optional[InterviewResult] = None
    last_feedback: Optional[InterviewFeedback] = None
    answered_count: int = 0
    created_at: Optional[datetime] = None


class InterviewSessionListItem(BaseModel):
    """GET /sessions 返回的列表单项"""
    session_id: str
    title: str
    type: str
    status: str = "unavailable"
    created_at: Optional[str] = None


class InterviewSessionListResponse(BaseModel):
    """GET /sessions 返回体"""
    sessions: List[InterviewSessionListItem] = Field(default_factory=list)
    total: int = 0
