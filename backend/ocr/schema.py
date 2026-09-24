"""Pydantic schema for one extracted field — the JSON shape a page's
extraction is validated against, taken directly from
scanned_form_extraction.md section 3. Anything that doesn't fit this shape
is a failed extraction for that page (see pipeline.py), not a best-effort
guess."""
from pydantic import BaseModel, Field, ValidationError, field_validator

CHECKBOX_STATES = {"checked", "unchecked", "ambiguous", None}


class OcrFieldOut(BaseModel):
    field_id: str
    question: str | None = None
    row_label: str | None = None
    column_label: str | None = None
    option_label: str | None = None
    text_value: str | None = None
    checkbox_state: str | None = None
    # The doc requires confidence to come from a real model/classifier output,
    # never fabricated. A general-purpose VLM has no calibrated log-prob
    # confidence exposed through a chat API, so this is the model's own
    # self-rating when it gives one — weaker evidence than genuine OCR/
    # classifier confidence, and callers should treat it that way, not as a
    # calibrated probability.
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("checkbox_state")
    @classmethod
    def _valid_checkbox_state(cls, v):
        if v is not None and v not in CHECKBOX_STATES:
            raise ValueError(f"checkbox_state must be one of {CHECKBOX_STATES}, got {v!r}")
        return v


class OcrPageOut(BaseModel):
    fields: list[OcrFieldOut] = Field(default_factory=list)


def _extract_complete_objects(raw: str) -> list[str] | None:
    """Scans raw text for a top-level '[' and returns every COMPLETE {...}
    object found inside it, in order — tolerant of the array (or the last
    object in it) being cut off mid-way, which is what a model running out of
    its response-length budget looks like. String contents (including a
    literal '{' or '}' inside a quoted value) are tracked so they never throw
    off the brace counting. Returns None only if no '[' is found at all."""
    start = raw.find("[")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    obj_start = None
    objects = []
    for i in range(start, len(raw)):
        ch = raw[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and obj_start is not None:
                objects.append(raw[obj_start:i + 1])
                obj_start = None
        elif ch == "]" and depth == 0:
            break
    return objects


def parse_page_fields_tolerant(raw_json: str) -> tuple[list[OcrFieldOut] | None, bool]:
    """Like parse_page_fields, but when the strict parse fails, salvages every
    COMPLETE field object from output that was cut off mid-array (the model
    ran out of its token budget before finishing). Returns
    (fields, was_truncated) — fields is None only if nothing at all could be
    salvaged; was_truncated tells the caller this is a partial result even
    though some fields did come back, so it can retry for a full page rather
    than silently accept less than what's actually on the page."""
    fields = parse_page_fields(raw_json)
    if fields is not None:
        return fields, False

    objects = _extract_complete_objects(raw_json)
    if not objects:
        return None, False

    import json
    recovered = []
    for obj_str in objects:
        try:
            recovered.append(OcrFieldOut.model_validate(json.loads(obj_str)))
        except Exception:
            continue  # one malformed object shouldn't lose every other one that did parse
    if not recovered:
        return None, False
    return recovered, True


def parse_page_fields(raw_json: str) -> list[OcrFieldOut] | None:
    """Validates the model's raw JSON output against the schema. Returns None
    (not []) on anything that doesn't parse or validate — an empty page is a
    real `fields: []`, a malformed response is a failure the caller must
    surface, never silently treat as 'no fields found'."""
    try:
        page = OcrPageOut.model_validate_json(raw_json)
    except ValidationError:
        try:
            # Also accept a bare JSON array (some models omit the {"fields": ...} wrapper).
            import json
            data = json.loads(raw_json)
            page = OcrPageOut(fields=data) if isinstance(data, list) else None
            if page is None:
                return None
        except Exception:
            return None
    except Exception:
        return None

    seen_ids = set()
    for f in page.fields:
        if f.field_id in seen_ids:
            f.field_id = f"{f.field_id}-dup{len(seen_ids)}"  # keep it, but never silently collapse two fields into one
        seen_ids.add(f.field_id)
    return page.fields
