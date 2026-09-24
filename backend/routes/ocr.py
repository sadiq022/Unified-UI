"""Document OCR routes — Phase 1 of scanned_form_extraction.md (see
document-ocr-implementation-plan.md for the full phase breakdown). Every
document belongs to one user; there is no sharing between users."""
import os
import shutil
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from backend.database import get_db, DATABASE_DIR
from backend.models import APIKey, OcrDocument, OcrPage, OcrField, User
from backend.schemas import OcrDocumentResponse, OcrDocumentDetailResponse, OcrFieldCorrection, OcrFieldResponse
from backend.auth import get_current_user
from backend.providers import is_known_provider, is_vision_model
from backend.ocr.renderer import render_to_pages, deskew
from backend.ocr.pipeline import run_ocr_pipeline

router = APIRouter(prefix="/api/ocr", tags=["Document OCR"])

UPLOAD_DIR = os.path.join(DATABASE_DIR, "ocr_uploads")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_PAGES = 30  # a safety cap — each page is its own model call


def _doc_dir(user_id: int, document_id: int) -> str:
    return os.path.join(UPLOAD_DIR, str(user_id), str(document_id))


@router.post("/documents", response_model=OcrDocumentResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    provider: str = Form("local"),
    model: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a scanned form (PDF/PNG/JPEG/TIFF). Rendering happens inline
    (fast); the actual page-by-page model extraction runs as a background
    task so this returns immediately with a "queued" document the frontend
    can poll. `provider` defaults to "local" for old clients/API callers that
    predate the multi-provider model picker."""
    if not is_known_provider(provider):
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")
    if not is_vision_model(provider, model):
        raise HTTPException(
            status_code=400,
            detail=f"{model} isn't a known vision-capable model for {provider}. Pick one from the model dropdown.",
        )

    key_result = await db.execute(
        select(APIKey).where(APIKey.user_id == current_user.id, APIKey.provider == provider)
    )
    key_obj = key_result.scalar_one_or_none()
    if not key_obj:
        raise HTTPException(status_code=400, detail=f"No API key configured for {provider}. Add one under Settings → API Keys.")

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File is too large (max 25MB).")

    filename = file.filename or "document"
    try:
        pages = render_to_pages(raw, filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not pages:
        raise HTTPException(status_code=400, detail="Couldn't find any pages in this file.")
    if len(pages) > MAX_PAGES:
        raise HTTPException(status_code=400, detail=f"This file has {len(pages)} pages; the limit is {MAX_PAGES}.")

    doc = OcrDocument(
        user_id=current_user.id, filename=filename, provider=provider, model=model,
        page_count=len(pages), status="queued",
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)

    doc_dir = _doc_dir(current_user.id, doc.id)
    os.makedirs(doc_dir, exist_ok=True)
    page_paths = []
    for i, page_image in enumerate(pages, start=1):
        page_image = deskew(page_image)
        path = os.path.join(doc_dir, f"page-{i}.png")
        page_image.save(path, "PNG")
        page_paths.append(path)
        db.add(OcrPage(
            document_id=doc.id, page_number=i, image_path=path,
            width=page_image.width, height=page_image.height, status="queued",
        ))
    await db.commit()

    background_tasks.add_task(run_ocr_pipeline, doc.id, provider, model, key_obj.api_key, page_paths)
    return doc


@router.get("/documents", response_model=list[OcrDocumentResponse])
async def list_documents(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(OcrDocument).where(OcrDocument.user_id == current_user.id).order_by(OcrDocument.created_at.desc())
    )
    return result.scalars().all()


async def _get_owned_document(document_id: int, db: AsyncSession, user_id: int, with_pages: bool = False) -> OcrDocument:
    query = select(OcrDocument).where(OcrDocument.id == document_id, OcrDocument.user_id == user_id)
    if with_pages:
        query = query.options(selectinload(OcrDocument.pages).selectinload(OcrPage.fields))
    doc = (await db.execute(query)).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/documents/{document_id}", response_model=OcrDocumentDetailResponse)
async def get_document(
    document_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return await _get_owned_document(document_id, db, current_user.id, with_pages=True)


@router.get("/documents/{document_id}/pages/{page_number}/image")
async def get_page_image(
    document_id: int, page_number: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    await _get_owned_document(document_id, db, current_user.id)  # ownership check
    page = (await db.execute(
        select(OcrPage).where(OcrPage.document_id == document_id, OcrPage.page_number == page_number)
    )).scalar_one_or_none()
    if not page or not os.path.exists(page.image_path):
        raise HTTPException(status_code=404, detail="Page image not found")
    return FileResponse(page.image_path, media_type="image/png")


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    doc = await _get_owned_document(document_id, db, current_user.id)
    await db.delete(doc)
    await db.commit()
    shutil.rmtree(_doc_dir(current_user.id, document_id), ignore_errors=True)
    return {"message": "Document deleted"}


@router.patch("/fields/{field_id}", response_model=OcrFieldResponse)
async def correct_field(
    field_id: int, data: OcrFieldCorrection,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """A human reviewer's correction — clears needs_review and marks the
    field as reviewed. Per scanned_form_extraction.md step 10, the correction
    replaces the value but the field is never deleted, so there's still a
    record of what the model originally extracted (in the log/history the
    frontend already showed before the edit)."""
    field = (await db.execute(
        select(OcrField).join(OcrPage).join(OcrDocument).where(
            OcrField.id == field_id, OcrDocument.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")

    if data.text_value is not None:
        field.text_value = data.text_value
    if data.checkbox_state is not None:
        if data.checkbox_state not in ("checked", "unchecked", "ambiguous"):
            raise HTTPException(status_code=400, detail="checkbox_state must be checked, unchecked, or ambiguous")
        field.checkbox_state = data.checkbox_state
    field.needs_review = False
    field.reviewed = True
    await db.commit()
    await db.refresh(field)
    return field
