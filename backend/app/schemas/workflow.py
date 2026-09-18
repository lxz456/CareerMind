# CareerMind AI Workflow Schemas
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Literal
from datetime import datetime


# ---- Path A: 规划提升 ----

class CareerPlanningRequest(BaseModel):
    """Request to start the career planning pipeline."""
    resume_id: Optional[str] = Field(None, description="已上传简历的 DB ID")
    resume_text: Optional[str] = Field(None, description="简历纯文本（如果没有 resume_id）")
    target_position: str = Field(..., min_length=1, max_length=100, description="必填目标岗位")
    target_location: Optional[Literal["us", "gb", "de", "jp", "sg", "hk", "tw"]] = Field(
        None,
        description="JSearch 求职国家/地区代码",
    )

    model_config = {"extra": "forbid"}

    @field_validator("target_position")      #字段级验证
    @classmethod
    def validate_target_position(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("目标岗位不能为空")
        return value

    @model_validator(mode="after")           #模型级验证
    def validate_resume_source(self):
        if bool(self.resume_id) == bool(self.resume_text and self.resume_text.strip()):
            raise ValueError("resume_id 和 resume_text 必须且只能提供一个")
        return self


class WorkflowStatusResponse(BaseModel):
    """路径 A 的职业规划任务状态。"""
    run_id: str
    path: str                          # career_planning
    status: str                        # pending | running | interrupted | completed | failed
    current_step: Optional[str] = None # resume_analysis | job_search | skill_gap | career_plan | summary
    completed_steps: List[str] = Field(default_factory=list)
    progress: float = 0.0              # 0–100
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class CareerPlanningResultResponse(BaseModel):
    """Complete result of the career planning pipeline."""
    run_id: str
    status: str
    resume_result: Optional[dict] = None       # Resume analysis node output
    job_result: Optional[dict] = None          # Job search node output
    skill_gap_result: Optional[dict] = None    # Skill gap node output
    career_plan_result: Optional[dict] = None  # Career plan node output
    summary: Optional[str] = None              # Final aggregated summary
    completed_steps: List[str] = Field(default_factory=list)


class CareerPlanningHistoryItem(BaseModel):
    """一条职业规划历史记录的摘要。"""
    run_id: str
    status: str
    progress: float = 0.0
    target_position: Optional[str] = None   # 从 input_data.target_position 取
    summary: Optional[str] = None
    error_code: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class CareerPlanningHistoryResponse(BaseModel):
    """用户的历史职业规划列表。"""
    plans: List[CareerPlanningHistoryItem] = Field(default_factory=list)
    total: int = 0
