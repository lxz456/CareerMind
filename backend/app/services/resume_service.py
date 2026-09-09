# CareerMind AI Resume Service
from fastapi import UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import ResumeRepo, UserRepo
from app.utils.file_parser import save_upload_file, extract_text
from app.schemas.resume import (
    ResumeUploadResponse,
    ResumeDetailResponse,
)


def calculate_resume_score(parsed_data: dict) -> float:
    """Calculate the existing completeness score for a parsed resume."""
    score = 0.0
    if parsed_data.get("name"):
        score += 10
    if parsed_data.get("skills"):
        score += min(len(parsed_data["skills"]) * 5, 30)
    if parsed_data.get("experience"):
        score += min(len(parsed_data["experience"]) * 10, 30)
    if parsed_data.get("education"):
        score += min(len(parsed_data["education"]) * 5, 15)
    if parsed_data.get("projects"):
        score += min(len(parsed_data["projects"]) * 5, 15)
    return score


class ResumeService:
    @staticmethod
    async def upload_and_extract(
        db: AsyncSession,
        user_id: str,
        file: UploadFile,
    ) -> ResumeUploadResponse:
        """Validate and store a resume, then extract text without invoking the LLM."""
        # Validate user exists
        user = await UserRepo.get_by_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Save file
        file_path = await save_upload_file(file, user_id)
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""

        # Create resume record
        resume = await ResumeRepo.create(
            db,
            user_id=user_id,
            original_filename=file.filename,
            file_path=file_path,
            file_type=ext,
            status="pending",
        )

        # Extract text once. Structured LLM analysis belongs to Path A.
        try:
            raw_text = extract_text(file_path, ext)
            if not raw_text.strip():
                raise ValueError("No text could be extracted from the resume file")
            resume.raw_text = raw_text
            resume.status = "ready"
            await db.flush()
        except Exception as e:
            resume.status = "failed"
            resume.analysis_summary = str(e)
            await db.flush()

        return ResumeUploadResponse.model_validate(resume)

    @staticmethod
    async def get_resume(
        db: AsyncSession,
        user_id: str,
        resume_id: str,
    ) -> ResumeDetailResponse:
        """Get a specific resume analysis result."""
        resume = await ResumeRepo.get_by_id_and_user(db, resume_id, user_id)
        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found")
        return ResumeDetailResponse.model_validate(resume)
