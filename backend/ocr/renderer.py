"""Ingest + render (scanned_form_extraction.md steps 1-2) and a minimal
version of step 3 (deskew only — perspective correction and the multiple
grayscale/denoise/threshold variants are a later phase; see
document-ocr-implementation-plan.md)."""
import io
import numpy as np
import cv2
import pymupdf as fitz  # pure-pip PDF rendering, no poppler/system dependency
from PIL import Image

RENDER_DPI = 300
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "tif", "tiff"}


def render_to_pages(raw: bytes, filename: str) -> list[Image.Image]:
    """PDF -> one Pillow image per page at RENDER_DPI. A plain image file is
    treated as a single-page document."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "pdf":
        pages = []
        zoom = RENDER_DPI / 72.0  # PDF points are 72/inch
        doc = fitz.open(stream=raw, filetype="pdf")
        try:
            for page in doc:
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                pages.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
        finally:
            doc.close()
        return pages
    if ext in IMAGE_EXTENSIONS:
        img = Image.open(io.BytesIO(raw))
        # TIFF can be multi-page too.
        frames = []
        try:
            while True:
                frames.append(img.convert("RGB").copy())
                img.seek(img.tell() + 1)
        except EOFError:
            pass
        return frames
    raise ValueError(f"Unsupported file type: .{ext}")


def deskew(image: Image.Image) -> Image.Image:
    """Corrects small page rotation (scanner skew) via a minimum-area
    bounding rectangle over the dark pixels. Leaves the image untouched if no
    clear skew angle is found — never distorts a page that's already straight."""
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = cv2.findNonZero(binary)
    if coords is None or len(coords) < 100:
        return image

    angle = cv2.minAreaRect(coords)[-1]
    # cv2.minAreaRect's angle convention wraps at 90 degrees; normalize to a
    # small correction only — this is meant to fix scanner skew (a couple of
    # degrees), not reorient an intentionally rotated page.
    if angle < -45:
        angle = 90 + angle
    if abs(angle) < 0.5 or abs(angle) > 15:
        return image  # not worth correcting, or too large to trust as "skew"

    (h, w) = gray.shape
    matrix = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    rotated = cv2.warpAffine(
        np.array(image), matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE,
    )
    return Image.fromarray(rotated)
