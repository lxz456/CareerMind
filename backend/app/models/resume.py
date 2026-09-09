# CareerMind AI Resume Model
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    # File info
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)  # pdf / docx

    # Parsed content (raw text)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Structured analysis result (LLM output)
    parsed_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # {
    #   "name": "",
    #   "summary": "",
    #   "skills": ["Python", "PyTorch", ...],
    #   "experience": [{"company": "", "title": "", "duration": "", "description": ""}],
    #   "education": [{"school": "", "degree": "", "major": "", "year": ""}],
    #   "projects": [{"name": "", "description": "", "tech_stack": []}],
    # }

    # Analysis metadata
    analysis_score: Mapped[float | None] = mapped_column(nullable=True)  # overall resume score
    analysis_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # pending -> ready (text extracted) -> processing -> completed/failed
    status: Mapped[str] = mapped_column(String(20), default="pending")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="resumes")
