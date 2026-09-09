# CareerMind AI Workflow Model
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, JSON, ForeignKey, Float, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    # Workflow type
    workflow_type: Mapped[str] = mapped_column(String(50), default="full_pipeline")
    # full_pipeline | resume_analysis | job_search | skill_gap | career_plan | interview

    # Status
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending | running | interrupted | waiting_user | completed | failed

    current_step: Mapped[str | None] = mapped_column(String(50), nullable=True)
    completed_steps: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Input
    input_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Results from each agent
    resume_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    job_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    skill_gap_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    career_plan_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Final summary
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Progress
    progress: Mapped[float | None] = mapped_column(Float, default=0.0)

    # LangGraph thread
    thread_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="workflow_runs")
