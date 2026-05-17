"""Celery task: analyze an uploaded employee handbook for state-law gaps.

Triggered by `POST /resources/handbook-gap-analyzer/analyze` after the PDF is
stored. The task:
    1. Pulls the PDF from storage.
    2. Asks Gemini multimodal to extract sections (title + excerpt).
    3. For each requested state, fetches the canonical required-topic set from
       jurisdiction_requirements (via handbook_service helpers).
    4. Asks Gemini to grade coverage of each requirement against the extracted
       sections, returning per-requirement {covered, severity, citation,
       what_good_looks_like}.
    5. Writes results to handbook_audit_reports.
"""

import asyncio
import json
import logging
import os
from typing import Any, Optional

from ..celery_app import celery_app
from ..utils import get_db_connection

logger = logging.getLogger(__name__)

SECTION_EXTRACT_TIMEOUT = 180
GAP_CHECK_TIMEOUT = 120
MAX_REQUIREMENTS_PER_STATE = 24  # cap per-state gemini call payload
MAX_SECTIONS_FOR_PROMPT = 80     # truncate uploaded sections for the prompt
SAMPLE_GAPS_COUNT = 2


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    name="app.workers.tasks.handbook_audit.analyze_handbook_audit",
)
def analyze_handbook_audit(self, report_id: str):
    """Sync entry-point invoked via .delay() from the upload route."""
    try:
        asyncio.run(_analyze_async(report_id))
    except Exception as exc:
        logger.exception("analyze_handbook_audit failed report_id=%s: %s", report_id, exc)
        try:
            asyncio.run(_mark_failed(report_id, str(exc)))
        except Exception:
            logger.exception("Could not mark report failed: %s", report_id)
        raise self.retry(exc=exc)


async def _analyze_async(report_id: str) -> None:
    conn = await get_db_connection()
    try:
        row = await conn.fetchrow(
            """
            SELECT id, states, industry, pdf_storage_path
            FROM handbook_audit_reports
            WHERE id = $1
            """,
            report_id,
        )
        if not row:
            logger.warning("handbook_audit row missing: %s", report_id)
            return

        states: list[str] = [s.upper() for s in (row["states"] or []) if s]
        industry: Optional[str] = row["industry"]
        pdf_path: str = row["pdf_storage_path"]
    finally:
        await conn.close()

    if not states or not pdf_path:
        await _mark_failed(report_id, "missing states or pdf_storage_path")
        return

    from app.core.services.storage import get_storage
    pdf_bytes = await get_storage().download_file(pdf_path)
    if not pdf_bytes:
        await _mark_failed(report_id, "PDF not retrievable from storage")
        return

    sections = await _extract_sections_from_pdf(pdf_bytes)
    if not sections:
        await _mark_failed(report_id, "Could not extract any sections from the uploaded PDF")
        return

    # Persist sections immediately so we have a checkpoint even if gap calls fail.
    conn = await get_db_connection()
    try:
        await conn.execute(
            """
            UPDATE handbook_audit_reports
            SET extracted_sections_jsonb = $2::jsonb
            WHERE id = $1
            """,
            report_id,
            json.dumps(sections),
        )
    finally:
        await conn.close()

    # Per-state gap detection.
    all_gaps: list[dict[str, Any]] = []
    state_summaries: dict[str, dict[str, int]] = {}

    from app.database import get_connection as _app_get_connection
    from app.core.services.handbook_service import _fetch_state_requirements

    for state in states:
        async with _app_get_connection() as conn:
            try:
                req_map = await _fetch_state_requirements(
                    conn,
                    [{"state": state, "city": None, "zipcode": None, "location_id": None}],
                )
            except Exception as exc:
                logger.warning("fetch_state_requirements failed for %s: %s", state, exc)
                req_map = {}
        state_requirements = req_map.get(state, [])
        if not state_requirements:
            logger.info("No jurisdiction requirements for %s; skipping", state)
            state_summaries[state] = {"critical": 0, "important": 0, "recommended": 0, "covered": 0}
            continue

        gaps = await _grade_state_coverage(
            state=state,
            industry=industry,
            requirements=state_requirements[:MAX_REQUIREMENTS_PER_STATE],
            sections=sections,
        )
        if gaps is None:
            logger.warning("Gap grading returned no result for %s", state)
            continue

        # gaps is a list of {requirement_key, requirement_title, covered, severity, ...}
        per_state = {"critical": 0, "important": 0, "recommended": 0, "covered": 0}
        for g in gaps:
            g["state"] = state
            if g.get("covered"):
                per_state["covered"] += 1
                continue
            sev = (g.get("severity") or "recommended").lower()
            if sev not in per_state:
                sev = "recommended"
            per_state[sev] += 1
            all_gaps.append(g)
        state_summaries[state] = per_state

    gap_counts = {
        "critical": sum(s.get("critical", 0) for s in state_summaries.values()),
        "important": sum(s.get("important", 0) for s in state_summaries.values()),
        "recommended": sum(s.get("recommended", 0) for s in state_summaries.values()),
        "by_state": state_summaries,
        "total_states": len(states),
        "total_gaps": len(all_gaps),
    }

    sample_gaps = _pick_sample_gaps(all_gaps, SAMPLE_GAPS_COUNT)

    conn = await get_db_connection()
    try:
        await conn.execute(
            """
            UPDATE handbook_audit_reports
            SET status = 'ready',
                gap_counts = $2::jsonb,
                gaps_jsonb = $3::jsonb,
                completed_at = NOW(),
                error_text = NULL
            WHERE id = $1
            """,
            report_id,
            json.dumps({**gap_counts, "sample_gaps": sample_gaps}),
            json.dumps(all_gaps),
        )
    finally:
        await conn.close()
    logger.info("handbook_audit ready report_id=%s gaps=%d", report_id, len(all_gaps))


async def _mark_failed(report_id: str, error_text: str) -> None:
    conn = await get_db_connection()
    try:
        await conn.execute(
            """
            UPDATE handbook_audit_reports
            SET status = 'failed',
                error_text = $2,
                completed_at = NOW()
            WHERE id = $1
            """,
            report_id,
            error_text[:1000],
        )
    finally:
        await conn.close()


def _pick_sample_gaps(gaps: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    severity_order = {"critical": 0, "important": 1, "recommended": 2}
    ranked = sorted(
        gaps,
        key=lambda g: (severity_order.get((g.get("severity") or "").lower(), 9), g.get("requirement_title") or ""),
    )
    out: list[dict[str, Any]] = []
    for g in ranked[:n]:
        out.append({
            "state": g.get("state"),
            "requirement_title": g.get("requirement_title"),
            "severity": g.get("severity"),
            "what_good_looks_like": (g.get("what_good_looks_like") or "")[:280],
        })
    return out


def _gemini_client():
    """Build a google-genai client using the same env wiring as gemini_compliance."""
    from google import genai
    from app.config import get_settings, load_settings

    try:
        settings = get_settings()
    except RuntimeError:
        settings = load_settings()
    if settings.use_vertex:
        return genai.Client(
            vertexai=True,
            project=settings.vertex_project,
            location=settings.vertex_location or "us-central1",
        )
    api_key = os.getenv("GEMINI_API_KEY") or settings.gemini_api_key
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")
    return genai.Client(api_key=api_key)


def _strip_json_fence(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


async def _extract_sections_from_pdf(pdf_bytes: bytes) -> list[dict[str, Any]]:
    """One Gemini multimodal call: extract handbook sections."""
    try:
        from google.genai import types
    except Exception as exc:
        logger.exception("google.genai import failed: %s", exc)
        return []

    try:
        client = _gemini_client()
    except Exception as exc:
        logger.exception("Gemini client init failed: %s", exc)
        return []

    prompt = (
        "You are reading an employee handbook PDF. Identify each distinct policy or "
        "section in the document. For each, capture the heading text, a 1-2 sentence "
        "verbatim excerpt that summarizes the policy, and the page range.\n\n"
        "Return ONLY JSON, no prose, with this shape:\n"
        '{"sections": [{"title": "string", "excerpt": "string", "page_range": "string"}]}\n\n'
        "Rules:\n"
        "- Up to 80 sections.\n"
        "- Skip cover pages, indexes, and signature pages.\n"
        "- Excerpt must be the actual handbook wording, not a paraphrase.\n"
        "- If page numbers are unclear, use \"?\"."
    )

    try:
        pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
    except Exception:
        # Older SDK shape.
        try:
            pdf_part = types.Part(inline_data=types.Blob(mime_type="application/pdf", data=pdf_bytes))
        except Exception as exc:
            logger.exception("Could not build PDF Part: %s", exc)
            return []

    model_name = os.getenv("HANDBOOK_AUDIT_MODEL", "gemini-2.5-flash")
    try:
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=model_name,
                contents=[pdf_part, prompt],
            ),
            timeout=SECTION_EXTRACT_TIMEOUT,
        )
    except Exception as exc:
        logger.exception("Section-extract Gemini call failed: %s", exc)
        return []

    raw = (getattr(response, "text", None) or "").strip()
    try:
        parsed = json.loads(_strip_json_fence(raw))
    except json.JSONDecodeError:
        logger.warning("Section-extract returned non-JSON: %s", raw[:200])
        return []
    sections = parsed.get("sections") if isinstance(parsed, dict) else None
    if not isinstance(sections, list):
        return []

    cleaned: list[dict[str, Any]] = []
    for s in sections:
        if not isinstance(s, dict):
            continue
        title = (s.get("title") or "").strip()
        excerpt = (s.get("excerpt") or "").strip()
        if not title:
            continue
        cleaned.append({
            "title": title[:240],
            "excerpt": excerpt[:600],
            "page_range": (s.get("page_range") or "").strip()[:32],
        })
    return cleaned[:MAX_SECTIONS_FOR_PROMPT]


async def _grade_state_coverage(
    *,
    state: str,
    industry: Optional[str],
    requirements: list[dict[str, Any]],
    sections: list[dict[str, Any]],
) -> Optional[list[dict[str, Any]]]:
    """Single Gemini call: grade coverage of each requirement against uploaded sections."""
    try:
        client = _gemini_client()
    except Exception as exc:
        logger.exception("Gemini client init failed: %s", exc)
        return None

    requirement_payload = []
    for req in requirements:
        requirement_payload.append({
            "key": (req.get("category") or req.get("title") or "")[:80],
            "title": (req.get("title") or "")[:160],
            "description": (req.get("description") or "")[:300],
            "source_url": req.get("source_url"),
        })

    section_payload = [
        {"title": s["title"], "excerpt": s["excerpt"]}
        for s in sections[:MAX_SECTIONS_FOR_PROMPT]
    ]

    prompt = (
        f"You are an employment-law analyst grading an employee handbook against {state} state law.\n"
        f"Industry context: {industry or 'general'}.\n\n"
        "I will give you (A) the list of legally-required topics for this state, and (B) the sections "
        "extracted from the uploaded handbook. For each required topic, decide whether the handbook "
        "covers it in a substantive way.\n\n"
        f"Requirements (A):\n{json.dumps(requirement_payload, indent=2)}\n\n"
        f"Handbook sections (B):\n{json.dumps(section_payload, indent=2)}\n\n"
        "Return ONLY JSON of this shape:\n"
        '{"results": [\n'
        '  {"requirement_key": "string", "requirement_title": "string", '
        '"covered": true|false, "severity": "critical|important|recommended", '
        '"citation": "short statute/regulator reference or null", '
        '"what_good_looks_like": "1-2 sentences describing the missing language", '
        '"matched_section_title": "string or null"}\n'
        ']}\n\n'
        "Rules:\n"
        "- One result per requirement, in the same order.\n"
        "- severity=critical when missing creates direct termination/liability exposure (e.g. anti-retaliation, "
        "harassment policy, mandated leave eligibility). severity=important when it is a state-mandated notice or "
        "policy. severity=recommended for best-practice items.\n"
        "- what_good_looks_like must describe the missing/weak content. Empty string if covered=true.\n"
        "- Do not invent statutes; if no specific citation is reliable, use null."
    )

    model_name = os.getenv("HANDBOOK_AUDIT_MODEL", "gemini-2.5-flash")
    try:
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
            ),
            timeout=GAP_CHECK_TIMEOUT,
        )
    except Exception as exc:
        logger.exception("Gap-grading Gemini call failed for %s: %s", state, exc)
        return None

    raw = (getattr(response, "text", None) or "").strip()
    try:
        parsed = json.loads(_strip_json_fence(raw))
    except json.JSONDecodeError:
        logger.warning("Gap-grading returned non-JSON for %s: %s", state, raw[:200])
        return None

    results = parsed.get("results") if isinstance(parsed, dict) else None
    if not isinstance(results, list):
        return None

    cleaned: list[dict[str, Any]] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        cleaned.append({
            "requirement_key": (r.get("requirement_key") or "")[:120],
            "requirement_title": (r.get("requirement_title") or "")[:240],
            "covered": bool(r.get("covered")),
            "severity": (r.get("severity") or "recommended").lower(),
            "citation": r.get("citation"),
            "what_good_looks_like": (r.get("what_good_looks_like") or "")[:600],
            "matched_section_title": r.get("matched_section_title"),
        })
    return cleaned
