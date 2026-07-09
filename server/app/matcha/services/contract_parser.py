"""Contract insurance-requirement auto-parse — Gemini reads an uploaded customer/
vendor/lease contract and extracts the insurance limits + endorsements the
counterparty requires, so limit-adequacy (#6/#28) can diff them against what the
company carries.

Best-effort, never raises — returns a draft the company reviews and confirms
before it drives the adequacy gaps. Mirrors ``loss_run_parser``: cached
IRAnalyzer, the PDF sent to Gemini as an inline part, JSON parsed back into the
contract-requirement shape, line names normalized to our coverage keys.
"""

import asyncio
import json
import logging
from typing import Optional

from app.config import get_settings
from app.matcha.services.ir_analysis import IRAnalyzer
from app.matcha.services import limit_adequacy as la
from app.matcha.services import risk_transfer as rt

logger = logging.getLogger(__name__)

_analyzer: Optional[IRAnalyzer] = None

_PROMPT = """You are an insurance contract analyst. From the attached CONTRACT (customer/vendor master service agreement, lease, construction subcontract, or similar), extract (a) the INSURANCE REQUIREMENTS the other party imposes on our client — i.e. the coverage the client must carry — and (b) the RISK-TRANSFER provisions (indemnification).

Return ONLY valid JSON with exactly these keys:
{"counterparty": "<the other party / customer name, or null>",
 "contract_type": "<one of: lease, construction, vendor_service, msa, other>",
 "governing_state": "<2-letter state code of the governing-law/choice-of-law clause, or null>",
 "project_state": "<2-letter state code where the work is performed or the premises sit, or null>",
 "requirements": [
   {"line": "<one of: General Liability, Commercial Auto, Umbrella/Excess, Workers Compensation, Employers Liability, Employment Practices, Professional Liability, Cyber, Property>",
    "per_occurrence": <required per-occurrence limit in whole dollars, or null>,
    "aggregate": <required aggregate limit in whole dollars, or null>,
    "additional_insured": <true if the contract requires additional-insured status>,
    "waiver_of_subrogation": <true if a waiver of subrogation is required>,
    "primary_noncontributory": <true if primary & non-contributory wording is required>,
    "note": "<short quote or paraphrase of the requirement, or null>",
    "quote": "<the requirement's exact wording, verbatim from the document, or null>",
    "page": <1-based page number the requirement appears on, or null>}
 ],
 "indemnity": {
   "present": <true if the contract contains an indemnification / hold-harmless clause>,
   "direction": "<one of: we_indemnify_them, they_indemnify_us, mutual, unclear>",
   "form": "<one of: broad, intermediate, limited, unclear>",
   "covers_sole_negligence": <true if the indemnitor must cover losses caused by the indemnitee's OWN SOLE negligence>,
   "defense_obligation": <true if the clause requires a duty to DEFEND, not merely to indemnify>,
   "quote": "<the operative indemnity language, verbatim from the document, or null>",
   "page": <1-based page number the indemnity clause appears on, or null>}}

Definitions for "form" — classify by how far the indemnity reaches into the INDEMNITEE's own fault:
  broad        = indemnitor covers the indemnitee even for the indemnitee's SOLE negligence.
  intermediate = indemnitor covers the indemnitee for the indemnitee's PARTIAL/concurrent negligence.
  limited      = indemnitor covers only losses caused by the INDEMNITOR's own negligence.
  unclear      = the clause exists but its reach cannot be determined from the text.

"direction" is from OUR CLIENT's perspective: we_indemnify_them means our client is the indemnitor.

Rules: only include lines the contract actually names. Convert "$1,000,000" / "$1M" / "one million" to 1000000. If a single combined limit is given, put it in per_occurrence. Every "quote" must be text copied EXACTLY from the document — never paraphrase into a quote field, and never invent a clause. If there is no indemnification clause, set indemnity.present to false and leave its other fields null/false. Do not invent requirements that are not in the document."""


def _get_analyzer() -> IRAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = IRAnalyzer(api_key=get_settings().gemini_api_key)
    return _analyzer


_MAX_QUOTE = 2000


def _text(v, limit: int) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s[:limit] or None


def _page(v) -> Optional[int]:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _state(v) -> Optional[str]:
    s = str(v or "").strip().upper()
    return s if len(s) == 2 and s.isalpha() else None


def _coerce_requirements(payload: dict) -> list[dict]:
    """Clamp model output into the stored requirement shape; normalize line keys,
    drop rows whose line we don't recognize."""
    out: list[dict] = []
    for req in payload.get("requirements") or []:
        if not isinstance(req, dict):
            continue
        line = la.normalize_line(req.get("line"))
        if not line:
            continue
        out.append({
            "line": line,
            "per_occurrence": la._num(req.get("per_occurrence")),
            "aggregate": la._num(req.get("aggregate")),
            "additional_insured": bool(req.get("additional_insured")),
            "waiver_of_subrogation": bool(req.get("waiver_of_subrogation")),
            "primary_noncontributory": bool(req.get("primary_noncontributory")),
            "note": _text(req.get("note"), 1000),
            "quote": _text(req.get("quote"), _MAX_QUOTE),
            "page": _page(req.get("page")),
        })
    return out


def _coerce_risk_transfer(payload: dict) -> Optional[dict]:
    """Clamp the indemnity block into the stored ``risk_transfer`` shape.

    Enum fields are whitelisted against ``risk_transfer``'s vocabulary — an
    unrecognized value degrades to ``unclear``, which the verdict engine treats
    as "needs review" rather than guessing.
    """
    ind = payload.get("indemnity")
    if not isinstance(ind, dict):
        return None
    if not ind.get("present"):
        return {"indemnity": {"present": False}}

    form = str(ind.get("form") or "").strip().lower()
    direction = str(ind.get("direction") or "").strip().lower()
    return {
        "indemnity": {
            "present": True,
            "form": form if form in rt.INDEMNITY_FORMS else "unclear",
            "direction": direction if direction in rt.INDEMNITY_DIRECTIONS else "unclear",
            "covers_sole_negligence": bool(ind.get("covers_sole_negligence")),
            "defense_obligation": bool(ind.get("defense_obligation")),
            "quote": _text(ind.get("quote"), _MAX_QUOTE),
            "page": _page(ind.get("page")),
        }
    }


def _coerce_contract_type(v) -> Optional[str]:
    s = str(v or "").strip().lower()
    return s if s in rt.CONTRACT_TYPES else None


async def parse_contract(pdf_bytes: bytes) -> dict:
    """Best-effort parse → the stored contract draft the company reviews and
    confirms. Never raises; on failure returns empty requirements with
    ``available=False``."""
    analyzer = _get_analyzer()
    payload: dict = {}
    try:
        from google.genai import types
        part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
        response = await asyncio.wait_for(
            analyzer.client.aio.models.generate_content(model=analyzer.model, contents=[_PROMPT, part]),
            timeout=90,
        )
        raw = (getattr(response, "text", None) or "").strip()
        payload = analyzer._parse_json_response(raw) or {}
    except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as exc:
        logger.warning("Contract parse failed: %s", exc)
        payload = {}
    return {
        "counterparty": (payload.get("counterparty") or None),
        "contract_type": _coerce_contract_type(payload.get("contract_type")),
        "governing_state": _state(payload.get("governing_state")),
        "project_state": _state(payload.get("project_state")),
        "requirements": _coerce_requirements(payload),
        "risk_transfer": _coerce_risk_transfer(payload),
        "available": bool(payload),
        "model": analyzer.model,
    }
