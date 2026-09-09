# CareerMind AI Resume API
from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.resume import ResumeUploadResponse, ResumeDetailResponse
from app.services.resume_service import ResumeService
from app.utils.security import get_current_user_id

router = APIRouter(prefix="/api/v1/resume", tags=["Resume"])

@router.post("/upload", response_model=ResumeUploadResponse, status_code=201)
async def upload_resume(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Upload a resume file and extract text for a later workflow analysis."""
    return await ResumeService.upload_and_extract(db, user_id, file)

@router.get("/{resume_id}", response_model=ResumeDetailResponse)
async def get_resume(
    resume_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get resume analysis result by ID."""
    return await ResumeService.get_resume(db, user_id, resume_id)
