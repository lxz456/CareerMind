# CareerMind AI Resume Schemas
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, List

class ExperienceItem(BaseModel):
    company: str = ""
    title: str = ""
    duration: str = ""
    description: str = ""

class EducationItem(BaseModel):
    school: str = ""
    degree: str = ""
    major: str = ""
    year: str = ""

class ProjectItem(BaseModel):
    name: str = ""
    description: str = ""
    tech_stack: List[str] = Field(default_factory=list)

class ResumeParsedData(BaseModel):
    name: Optional[str] = None
    summary: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    experience: List[ExperienceItem] = Field(default_factory=list)
    education: List[EducationItem] = Field(default_factory=list)
    projects: List[ProjectItem] = Field(default_factory=list)
    skill_levels: dict = Field(default_factory=dict)

class ResumeUploadResponse(BaseModel):
    id: str
    original_filename: str
    file_type: str
    status: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

class ResumeDetailResponse(BaseModel):
    id: str
    original_filename: str
    file_type: str
    status: str
    parsed_data: Optional[ResumeParsedData] = None
    analysis_score: Optional[float] = None
    analysis_summary: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
