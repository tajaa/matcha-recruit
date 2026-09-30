"""Signed-copy check and filing for an HR case (6/6).

The manager (or HR) uploads the signed write-up after delivery. It is filed
straight away in Drive `HR / Discipline / Signed / <Last, First>` under the
company's filename template — the format is produced, not merely checked —
and then read:

1. `inspect_pdf` — deterministic: is it a PDF, encrypted, how many pages,
   is there a text layer. Images (a phone photo of the signed page) skip this.
2. `read_signed_copy` — one Gemini multimodal read (parse-only): legible,
   signed, printed name matches, manager signature, employee comments,
   refusal noted, matches the approved letter, pages complete.
3. `decide` — pure: `verified` or `needs_attention` with plain-language
   reasons. **A check that couldn't run is never a pass**
   (`check_unavailable` → needs_attention).

Employee comments always flag HR. The transcribed comment is stored on the
case for the HR panel; notification bodies say only that there are comments.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

FILENAME_TOKENS = (
    "last_name", "first_name", "action_type", "infraction_type",
    "delivered_date", "case_number", "incident_number",
)
DEFAULT_TEMPLATE = "{last_name}_{first_name}_{action_type}_{delivered_date}"
SIGNED_EXTENSIONS = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
_TOKEN_RE = re.compile(r"\{([^{}]*)\}")
_READ_TIMEOUT = 90

REASON_TEXT = {
    "unreadable_pdf": "The file isn't a readable PDF.",
    "encrypted_pdf": "The PDF is password-protected, so it can't be checked.",
    "empty_pdf": "The PDF has no pages.",
    "illegible_scan": "The scan is too hard to read.",
    "employee_signature_missing": "There's no employee signature on it.",
    "signature_name_mismatch": "The printed name doesn't match the employee.",
    "letter_mismatch": "It doesn't look like the letter HR approved.",
    "pages_missing": "Pages look to be missing.",
    "employee_comments": "The employee wrote comments on it.",
    "refusal_noted": "It says the employee refused to sign.",
    "check_unavailable": "The automatic check couldn't run, so a person needs to look at it.",
}


class TemplateError(ValueError):
    pass


# ── Filename ────────────────────────────────────────────────────────────


def validate_template(template: str) -> str:
    template = (template or "").strip()
    if not template or len(template) > 200:
        raise TemplateError("The filename format must be 1–200 characters.")
    tokens = _TOKEN_RE.findall(template)
    if not tokens:
        raise TemplateError("The filename format needs at least one field, like {last_name}.")
    unknown = sorted({t for t in tokens if t not in FILENAME_TOKENS})
    if unknown:
        raise TemplateError(
            "Unknown field(s): " + ", ".join("{" + t + "}" for t in unknown)
            + ". Use: " + ", ".join("{" + t + "}" for t in FILENAME_TOKENS) + "."
        )
    if "{" in _TOKEN_RE.sub("", template) or "}" in _TOKEN_RE.sub("", template):
        raise TemplateError("The filename format has an unmatched brace.")
    return template


def _slug(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", " ", text)
    return re.sub(r"\s+", "-", text).strip("-.") or "unknown"


def render_filename(template: str, *, values: dict[str, Any], extension: str) -> str:
    """Pure. Unknown tokens can't occur (validated on save); a stored template
    that somehow carries one falls back to the default rather than leaking
    braces into a filename."""
    try:
        template = validate_template(template)
    except TemplateError:
        template = DEFAULT_TEMPLATE
    name = _TOKEN_RE.sub(lambda m: _slug(values.get(m.group(1))), template)
    name = re.sub(r"[-_]{3,}", "_", name).strip("-_.")[:150] or "signed-write-up"
    return f"{name}{extension}"


def filename_values(case: dict[str, Any], employee: dict[str, Any]) -> dict[str, Any]:
    delivered = case.get("delivered_at")
    if isinstance(delivered, datetime):
        delivered = delivered.date()
    inputs = (case.get("review") or {}).get("input") or {}
    return {
        "last_name": employee.get("last_name"),
        "first_name": employee.get("first_name"),
        "action_type": (case.get("action_type") or "write-up").replace("_", "-"),
        "infraction_type": (inputs.get("infraction_type") or "").replace("_", "-") or None,
        "delivered_date": (delivered or date.today()).isoformat(),
        "case_number": case.get("case_number"),
        "incident_number": case.get("incident_number"),
    }


# ── Inspection + reading ────────────────────────────────────────────────


def inspect_pdf(data: bytes) -> dict[str, Any]:
    """Deterministic facts about a PDF. Never raises."""
    out = {"is_pdf": False, "encrypted": False, "page_count": 0, "has_text_layer": False}
    if not data or not data[:1024].lstrip().startswith(b"%PDF"):
        return out
    try:
        import fitz  # PyMuPDF

        with fitz.open(stream=data, filetype="pdf") as doc:
            out["is_pdf"] = True
            out["encrypted"] = bool(doc.needs_pass)
            if doc.needs_pass:
                return out
            out["page_count"] = doc.page_count
            out["has_text_layer"] = any(page.get_text().strip() for page in doc)
    except Exception:
        logger.warning("[hr_cases] could not open signed PDF", exc_info=True)
        out["is_pdf"] = False
    return out


_READ_PROMPT = """You are checking a SIGNED corrective-action letter an employer scanned in.
Report what you can SEE. Do not judge whether the discipline was fair or lawful.

The employee's name is: {employee_name}
The letter HR approved begins:
---
{letter_excerpt}
---

Return STRICT JSON, no markdown fence:
{{"legible": true|false,
  "employee_signature_present": true|false,
  "employee_signature_date": "YYYY-MM-DD" | null,
  "printed_name_matches": true|false|null,
  "manager_signature_present": true|false,
  "employee_comments_present": true|false,
  "employee_comments_text": "<verbatim, or null>",
  "refusal_noted": true|false,
  "matches_letter": true|false|null,
  "pages_look_complete": true|false}}
"""

_BOOL_FIELDS = (
    "legible", "employee_signature_present", "manager_signature_present",
    "employee_comments_present", "refusal_noted", "pages_look_complete",
)
_TRI_FIELDS = ("printed_name_matches", "matches_letter")


def _coerce_reading(data: Any) -> dict[str, Any]:
    data = data if isinstance(data, dict) else {}
    out: dict[str, Any] = {"available": True}
    for key in _BOOL_FIELDS:
        out[key] = data.get(key) is True
    for key in _TRI_FIELDS:
        value = data.get(key)
        out[key] = value if isinstance(value, bool) else None
    comment = data.get("employee_comments_text")
    out["employee_comments_text"] = str(comment).strip()[:2000] if comment else None
    signed = data.get("employee_signature_date")
    out["employee_signature_date"] = str(signed)[:10] if signed else None
    # Required fields missing entirely = the model didn't answer; treat as unavailable.
    if not all(key in data for key in ("legible", "employee_signature_present")):
        out["available"] = False
    return out


async def read_signed_copy(data: bytes, *, mime_type: str, employee_name: Optional[str], letter_text: Optional[str]) -> dict[str, Any]:
    """One multimodal read. Never raises: failure → {"available": False}."""
    try:
        from google.genai import types

        from app.core.services.ai_usage import feature_scope
        from app.core.services.model_catalog import GEMINI_FLASH
        from app.matcha.services._shared.citations import _parse_json
        from app.matcha.services._shared.gemini import _genai

        prompt = _READ_PROMPT.format(
            employee_name=employee_name or "(unknown)",
            letter_excerpt=(letter_text or "(not available)")[:3000],
        )
        part = types.Part.from_bytes(data=data, mime_type=mime_type)
        with feature_scope("matcha.hr_cases.signed_copy"):
            resp = await asyncio.wait_for(
                _genai().aio.models.generate_content(model=GEMINI_FLASH, contents=[prompt, part]),
                timeout=_READ_TIMEOUT,
            )
        return _coerce_reading(_parse_json(getattr(resp, "text", "") or ""))
    except Exception:
        logger.warning("[hr_cases] signed-copy read failed", exc_info=True)
        return {"available": False}


def decide(inspection: Optional[dict[str, Any]], reading: dict[str, Any], *, esigned: bool = False) -> dict[str, Any]:
    """Pure. `inspection` is None for an image upload."""
    reasons: list[str] = []
    if inspection is not None:
        if not inspection.get("is_pdf"):
            reasons.append("unreadable_pdf")
        elif inspection.get("encrypted"):
            reasons.append("encrypted_pdf")
        elif inspection.get("page_count", 0) == 0:
            reasons.append("empty_pdf")
    if not reading.get("available"):
        reasons.append("check_unavailable")
    else:
        if not reading.get("legible"):
            reasons.append("illegible_scan")
        if not reading.get("employee_signature_present") and not esigned and not reading.get("refusal_noted"):
            reasons.append("employee_signature_missing")
        if reading.get("printed_name_matches") is False:
            reasons.append("signature_name_mismatch")
        if reading.get("matches_letter") is False:
            reasons.append("letter_mismatch")
        if not reading.get("pages_look_complete"):
            reasons.append("pages_missing")
        if reading.get("refusal_noted"):
            reasons.append("refusal_noted")
        if reading.get("employee_comments_present"):
            reasons.append("employee_comments")
    reasons = list(dict.fromkeys(reasons))
    return {
        "outcome": "needs_attention" if reasons else "verified",
        "reasons": reasons,
        "reason_text": [REASON_TEXT[r] for r in reasons],
        "flag_hr_comments": "employee_comments" in reasons,
    }


# ── Filing + running the check ──────────────────────────────────────────


async def ensure_employee_folder(conn, *, company_id: UUID, employee: dict[str, Any]) -> UUID:
    """`HR / Discipline / Signed / <Last, First>` — created on first use."""
    from app.matcha.services.drive import drive_service

    folders = await drive_service.ensure_system_folders(conn, company_id)
    parent = folders["hr_discipline_signed"]
    last = (employee.get("last_name") or "").strip()
    first = (employee.get("first_name") or "").strip()
    name = drive_service.clean_folder_name(", ".join(p for p in (last, first) if p) or "Unknown employee")
    existing = await conn.fetchval(
        "SELECT id FROM drive_folders WHERE company_id = $1 AND parent_id = $2 AND lower(name) = lower($3)",
        company_id, parent, name,
    )
    if existing:
        return existing
    return await conn.fetchval(
        """
        INSERT INTO drive_folders (company_id, parent_id, space, name)
        VALUES ($1, $2, 'hr', $3)
        ON CONFLICT DO NOTHING
        RETURNING id
        """,
        company_id, parent, name,
    ) or await conn.fetchval(
        "SELECT id FROM drive_folders WHERE company_id = $1 AND parent_id = $2 AND lower(name) = lower($3)",
        company_id, parent, name,
    )


def validate_signed_upload(filename: str, data: bytes) -> tuple[str, str]:
    """(extension, mime). Raises ValueError with a user-facing message."""
    import os

    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in SIGNED_EXTENSIONS:
        raise ValueError("Upload the signed copy as a PDF or a photo (PNG or JPG).")
    if not data:
        raise ValueError("That file is empty.")
    from app.matcha.services.drive.drive_service import MAX_FILE_BYTES

    if len(data) > MAX_FILE_BYTES:
        raise ValueError("Files can be at most 25 MB.")
    return ext, SIGNED_EXTENSIONS[ext]


async def run_check(conn, *, company_id: UUID, case_id: UUID, data: bytes, mime_type: str,
                    actor_user_id: Optional[UUID]) -> dict[str, Any]:
    """Read the signed copy and move the case to closed or needs_attention.
    Returns the updated case. Notifications are sent by the caller's layer."""
    from . import case_service

    case = await case_service.get_case(conn, company_id=company_id, case_id=case_id)
    employee = await conn.fetchrow(
        "SELECT first_name, last_name FROM employees WHERE id = $1", case.get("employee_id"),
    ) if case.get("employee_id") else None
    employee_name = " ".join(p for p in ((employee or {}).get("first_name"), (employee or {}).get("last_name")) if p) or None
    letter_text = None
    if case.get("draft_file_id"):
        letter_text = await conn.fetchval("SELECT extracted_text FROM drive_files WHERE id = $1", case["draft_file_id"])
    inspection = inspect_pdf(data) if mime_type == "application/pdf" else None
    reading = await read_signed_copy(data, mime_type=mime_type, employee_name=employee_name, letter_text=letter_text)
    verdict = decide(inspection, reading)
    verification = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "inspection": inspection,
        "reading": {k: v for k, v in reading.items()},
        **verdict,
    }
    if verdict["outcome"] == "verified":
        return await case_service.apply_event(
            conn, company_id=company_id, case_id=case_id, event="verified", actor_user_id=actor_user_id,
            sets={"verification": verification, "attention_reasons": []},
        )
    return await case_service.apply_event(
        conn, company_id=company_id, case_id=case_id, event="attention", actor_user_id=actor_user_id,
        sets={"verification": verification, "attention_reasons": verdict["reasons"]},
        details={"reasons": verdict["reasons"]},
    )
