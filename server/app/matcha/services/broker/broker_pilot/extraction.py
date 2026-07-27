"""Per-upload document processing: the classify+extract prompt, coercion of the
model's JSON into the stored extraction shape, and extract_document. A Gemini
failure here degrades the document to text_only rather than raising.
"""
import asyncio
import logging
from app.matcha.services._shared.citations import _parse_json

from ._config import DOC_TYPES, MODEL, _GEMINI_TIMEOUT, _LINES, _MAX_KEY_FIGURES, _MAX_NOTABLE, _STORED_TEXT_CAP
from app.matcha.services._shared.gemini import _genai
from .chat import _why_empty

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Document extraction — one Gemini pass at upload time (classify + summarize
# + pull the figures a broker would cite). Never raises.
# --------------------------------------------------------------------------- #

_EXTRACT_PROMPT = """You are a commercial P&C insurance analyst. Classify the attached document and extract its citable substance.

Return ONLY valid JSON, exactly this shape:
{"doc_type": "<one of: loss_run | dec_page | quote | carrier_letter | bordereau | policy_form | financials | contract | other>",
 "title": "<short document title, e.g. 'Travelers WC loss run valued 2026-03-31'>",
 "carrier": "<carrier/issuer name or null>",
 "line": "<one of: wc | gl | auto | property | package | umbrella | epl | cyber | other, or null>",
 "period_label": "<policy period / valuation label shown, or null>",
 "effective_date": "<YYYY-MM-DD if the document shows an effective/valuation date, else null>",
 "summary": "<neutral 2-4 sentence summary of what this document is and shows, max 600 chars>",
 "key_figures": [{"label": "<what the figure is>", "value": "<the figure as shown>", "context": "<where/what it applies to>"}],
 "notable": ["<red flags, exclusions, conditions, endorsements, or anomalies worth a broker's attention>"]}

Rules:
- Extract ONLY what the document actually shows. Never invent, estimate, or infer figures.
- key_figures: at most 20 — premiums, limits, retentions/deductibles, claim counts, paid/reserved totals, mods, rates. The numbers a broker would cite.
- notable: at most 10 short items.
- doc_type "contract": a client/vendor/lease/MSA/subcontract agreement carrying insurance requirements or an indemnification clause — NOT an insurance policy form (that is policy_form).
- If the document is unreadable or not an insurance-related document, use doc_type "other" and say so in the summary."""


def _coerce_extraction(payload: dict) -> dict:
    """Clamp the model's extraction into the stored schema. Pure."""
    if not isinstance(payload, dict):
        payload = {}
    doc_type = str(payload.get("doc_type") or "").strip().lower()
    if doc_type not in DOC_TYPES:
        doc_type = "other"
    line = str(payload.get("line") or "").strip().lower() or None
    if line is not None and line not in _LINES:
        line = None

    def _s(key: str, cap: int):
        v = payload.get(key)
        return str(v).strip()[:cap] if v else None

    raw_figures = payload.get("key_figures")
    if not isinstance(raw_figures, list):
        raw_figures = []
    raw_notable = payload.get("notable")
    if not isinstance(raw_notable, list):
        raw_notable = []
    figures = []
    for f in raw_figures[:_MAX_KEY_FIGURES]:
        if not isinstance(f, dict):
            continue
        label = str(f.get("label") or "").strip()[:80]
        value = str(f.get("value") or "").strip()[:60]
        if not (label and value):
            continue
        figures.append({
            "label": label, "value": value,
            "context": str(f.get("context") or "").strip()[:160],
        })
    notable = [
        str(n).strip()[:200] for n in raw_notable[:_MAX_NOTABLE]
        if n and str(n).strip()
    ]
    return {
        "doc_type": doc_type,
        "title": _s("title", 200),
        "carrier": _s("carrier", 120),
        "line": line,
        "period_label": _s("period_label", 60),
        "effective_date": _s("effective_date", 10),
        "summary": _s("summary", 600),
        "key_figures": figures,
        "notable": notable,
    }


async def extract_document(data: bytes | None, text: str | None, *, is_pdf: bool,
                           filename: str) -> dict:
    """One-shot classify+extract. Best-effort, never raises —
    returns ``{"extraction": {...}, "available": bool}``."""
    payload: dict = {}
    try:
        from google.genai import types
        if is_pdf and data:
            part = types.Part.from_bytes(data=data, mime_type="application/pdf")
            contents = [f"{_EXTRACT_PROMPT}\n\nFILENAME: {filename}", part]
        else:
            contents = (
                f"{_EXTRACT_PROMPT}\n\nFILENAME: {filename}\n\n"
                f"DOCUMENT TEXT:\n{(text or '')[:_STORED_TEXT_CAP]}"
            )
        resp = await asyncio.wait_for(
            _genai().aio.models.generate_content(
                model=MODEL, contents=contents,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            ),
            timeout=_GEMINI_TIMEOUT,
        )
        payload = _parse_json(getattr(resp, "text", "") or "")
        if not payload:
            logger.warning("broker_pilot: unparseable extraction reply for %s — %s",
                           filename, _why_empty(resp))
    except Exception as exc:  # noqa: BLE001 - degrade to text_only, never 500 the upload
        logger.warning("broker_pilot: document extraction failed for %s: %s", filename, exc)
        payload = {}
    # `available` means the model produced a usable classification — not merely
    # any JSON. A degenerate `{}` reply must land text_only, not "ready".
    available = bool(payload.get("doc_type") or payload.get("summary")
                     or payload.get("key_figures")) if isinstance(payload, dict) else False
    return {"extraction": _coerce_extraction(payload), "available": available}
