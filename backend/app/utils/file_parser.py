# CareerMind AI File Parser Utility
import re
import uuid
from pathlib import Path
from fastapi import UploadFile, HTTPException, status

from app.config import get_settings

settings = get_settings()

ALLOWED_EXTENSIONS = {"pdf", "docx"}

def validate_file(file: UploadFile) -> str:
    """Validate uploaded file and return file extension."""
    original = file.filename or "unknown"
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type .{ext} not allowed. Accepted: pdf, docx",
        )
    return ext

async def save_upload_file(file: UploadFile, user_id: str) -> str:
    """Save uploaded file to disk, return file path."""
    validate_file(file)
    upload_dir = Path(settings.UPLOAD_DIR) / user_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    original_name = Path(file.filename or "resume").name
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", original_name)
    file_path = upload_dir / f"{uuid.uuid4().hex}_{safe_name}"

    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Max {settings.MAX_UPLOAD_SIZE_MB}MB",
        )

    with open(file_path, "wb") as f:
        f.write(content)

    return str(file_path)

def extract_text_pdf(file_path: str) -> str:
    """Extract text from PDF file."""
    text_parts = []
    try:
        import fitz  # pymupdf
        doc = fitz.open(file_path)
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
    except ImportError:
        from PyPDF2 import PdfReader
        reader = PdfReader(file_path)
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
    return "\n".join(text_parts)

def extract_text_docx(file_path: str) -> str:
    """Extract text from DOCX file."""
    from docx import Document
    doc = Document(file_path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

def extract_text(file_path: str, file_type: str) -> str:
    """Extract text from file based on type."""
    if file_type == "pdf":
        return extract_text_pdf(file_path)
    elif file_type == "docx":
        return extract_text_docx(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")
