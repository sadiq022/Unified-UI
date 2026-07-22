import io
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from backend.models import User
from backend.auth import get_current_user

router = APIRouter(prefix="/api/files", tags=["Files"])

MAX_CHARS = 32_000
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB raw file size guard

TEXT_EXTENSIONS = {
    "txt", "md", "markdown", "csv", "json", "log", "yaml", "yml",
    "py", "js", "jsx", "ts", "tsx", "html", "css", "xml", "ini", "cfg",
}


def _extract_pdf_text(raw: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(raw))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _extract_docx_text(raw: bytes) -> str:
    import docx
    document = docx.Document(io.BytesIO(raw))
    return "\n".join(p.text for p in document.paragraphs)


def _extract_plain_text(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


@router.post("/extract-text")
async def extract_text(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Extract text from an uploaded document (PDF/DOCX/plain text), truncated to 32k characters."""
    filename = file.filename or "file"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File is too large (max 20MB).")

    try:
        if ext == "pdf":
            text = _extract_pdf_text(raw)
        elif ext == "docx":
            text = _extract_docx_text(raw)
        elif ext in TEXT_EXTENSIONS or not ext:
            text = _extract_plain_text(raw)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: .{ext}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not extract text from this file: {e}")

    text = text.strip()
    truncated = len(text) > MAX_CHARS
    if truncated:
        text = text[:MAX_CHARS]

    return {
        "filename": filename,
        "content": text,
        "truncated": truncated,
        "char_count": len(text),
    }
