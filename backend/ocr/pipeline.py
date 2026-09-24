"""Runs the extraction pipeline for one uploaded document, one page at a
time, in a background task. Phase 1: a single vision-model call per whole
page stands in for steps 4-8 of scanned_form_extraction.md (layout
detection, crop generation, OCR, checkbox classification, LLM
interpretation) — see document-ocr-implementation-plan.md for what a later
phase adds (per-checkbox crops, a dedicated geometry/state detector,
multi-variant preprocessing comparison, a real review queue UI)."""
import asyncio
import base64
import time
import traceback
from sqlalchemy import select

from backend.database import async_session
from backend.models import OcrDocument, OcrPage, OcrField
from backend.providers import get_provider
from backend.ocr.prompts import EXTRACTION_SYSTEM_PROMPT
from backend.ocr.schema import parse_page_fields_tolerant
from backend.text_cleanup import strip_think_blocks

# A dense real-world form (many rows/columns/checkboxes) can need far more
# than a first guess allows — the model then gets cut off mid-JSON and the
# whole page used to be lost. Local inference has no per-token cost, so it's
# cheap to start generous and retry even bigger before giving up.
EXTRACTION_MAX_TOKENS = 16000
RETRY_MAX_TOKENS = 30000
# Below this self-reported confidence (or when there isn't one), a field is
# flagged for human review rather than trusted outright.
REVIEW_CONFIDENCE_THRESHOLD = 0.6
# Pages are read concurrently instead of one at a time — matches a local
# llama-server's default slot count, and is also a reasonable ceiling for a
# cloud provider's per-minute rate limit. Raise it if your local server has
# more slots, or lower it if a cloud provider starts throttling requests.
MAX_CONCURRENT_PAGES = 4


def _needs_review(field) -> bool:
    if field.checkbox_state == "ambiguous":
        return True
    if field.confidence is None or field.confidence < REVIEW_CONFIDENCE_THRESHOLD:
        return True
    return False


async def _call_model(provider_name: str, model: str, api_key: str, data_url: str, max_tokens: int) -> str:
    result = await get_provider(provider_name).chat(
        [{"role": "user", "content": EXTRACTION_SYSTEM_PROMPT, "image": data_url}],
        model, api_key, max_tokens=max_tokens, temperature=0.1,
    )
    return strip_think_blocks(result.get("content", ""))


async def _extract_page(provider_name: str, model: str, api_key: str, png_bytes: bytes) -> tuple[list, str | None]:
    """Returns (fields, warning). warning is set (but fields still returned)
    when the response was cut off before finishing even after retrying with a
    bigger budget — the page isn't silently treated as complete in that case."""
    data_url = f"data:image/png;base64,{base64.b64encode(png_bytes).decode()}"

    content = await _call_model(provider_name, model, api_key, data_url, EXTRACTION_MAX_TOKENS)
    fields, truncated = parse_page_fields_tolerant(content)
    if fields is not None and not truncated:
        return fields, None

    # Unparseable outright, or salvaged-but-cut-off — try once more with a
    # much larger budget before accepting a partial (or empty) result.
    content2 = await _call_model(provider_name, model, api_key, data_url, RETRY_MAX_TOKENS)
    fields2, truncated2 = parse_page_fields_tolerant(content2)
    if fields2 is not None and not truncated2:
        return fields2, None

    best_fields, best_content = max(
        ((fields, content), (fields2, content2)),
        key=lambda pair: len(pair[0]) if pair[0] is not None else -1,
    )
    if best_fields is None:
        raise ValueError(f"model returned unparseable output even after retrying with a larger budget: {content2[:300]!r}")
    warning = (
        f"The model's response was cut off before finishing this page — {len(best_fields)} field(s) were "
        "recovered, but the page may be incomplete. Try again, or pick a model that allows longer responses."
    )
    print(f"[ocr] page extraction truncated even after retry, kept {len(best_fields)} fields: {best_content[:150]!r}")
    return best_fields, warning


async def _process_page(
    document_id: int, page_number: int, path: str, provider_name: str, model: str, api_key: str,
    semaphore: asyncio.Semaphore,
) -> str:
    """Runs one page end to end (mark processing, extract, store fields, mark
    done/failed) and returns its outcome as a plain string ('ok', 'partial',
    or 'failed') rather than mutating shared counters — this runs concurrently
    with sibling pages, each in its own DB session, so results are aggregated
    by the caller after they've all finished instead of being raced here."""
    async with semaphore:
        async with async_session() as db:
            page = (await db.execute(
                select(OcrPage).where(
                    OcrPage.document_id == document_id, OcrPage.page_number == page_number,
                )
            )).scalar_one_or_none()
            if page is None:
                return "ok"  # document was deleted mid-run — nothing to do
            page.status = "processing"
            await db.commit()
            page_started_at = time.monotonic()

            try:
                with open(path, "rb") as f:
                    png_bytes = f.read()
                fields, warning = await _extract_page(provider_name, model, api_key, png_bytes)
                for f in fields:
                    db.add(OcrField(
                        page_id=page.id,
                        field_id=f.field_id,
                        question=f.question,
                        row_label=f.row_label,
                        column_label=f.column_label,
                        option_label=f.option_label,
                        text_value=f.text_value,
                        checkbox_state=f.checkbox_state,
                        confidence=f.confidence,
                        bbox_page=None,  # no real geometry yet — see module docstring
                        crop_id="page",
                        needs_review=_needs_review(f),
                    ))
                page.status = "done"
                page.error = warning  # None on a clean full read; set (but still "done") when partial
                outcome = "partial" if warning else "ok"
            except Exception as e:
                print(f"[ocr] page {page_number} of document {document_id} failed: {type(e).__name__}: {e}")
                traceback.print_exc()
                page.status = "failed"
                page.error = f"{type(e).__name__}: {e}"
                outcome = "failed"
            page.processing_seconds = time.monotonic() - page_started_at
            await db.commit()
            return outcome


async def run_ocr_pipeline(document_id: int, provider_name: str, model: str, api_key: str, page_paths: list[str]):
    """page_paths: rendered PNG file paths, absolute, one per page, in order.
    Pages are read concurrently (see MAX_CONCURRENT_PAGES) — same model, same
    provider, just no longer waiting for one page to finish before starting
    the next."""
    started_at = time.monotonic()
    async with async_session() as db:
        doc = await db.get(OcrDocument, document_id)
        if doc is None:
            return  # deleted before the background task got to run
        doc.status = "processing"
        await db.commit()

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_PAGES)
    outcomes = await asyncio.gather(*(
        _process_page(document_id, page_number, path, provider_name, model, api_key, semaphore)
        for page_number, path in enumerate(page_paths, start=1)
    ))
    any_ok = "ok" in outcomes or "partial" in outcomes
    any_partial = "partial" in outcomes
    any_failed = "failed" in outcomes

    async with async_session() as db:
        doc = await db.get(OcrDocument, document_id)
        if doc is None:
            return
        doc.status = "done" if any_ok else "failed"
        doc.processing_seconds = time.monotonic() - started_at
        if any_failed and not any_ok:
            doc.error = "Every page failed to process — see individual page errors."
        elif any_failed and any_partial:
            doc.error = "Some pages failed, and some pages may be incomplete — see individual page notes."
        elif any_failed:
            doc.error = "Some pages failed to process — see individual page errors."
        elif any_partial:
            doc.error = "Some pages may be incomplete — see individual page notes."
        await db.commit()
