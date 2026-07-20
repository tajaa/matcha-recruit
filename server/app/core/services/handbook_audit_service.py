"""Handbook audit pipeline — runs inline via FastAPI BackgroundTasks.

Triggered by ``POST /resources/handbook-gap-analyzer/analyze`` after the
PDF is stored. The pipeline:

    1. Pulls the PDF from storage.
    2. Asks Gemini multimodal to extract sections (title + excerpt).
    3. For each requested state, fetches the canonical required-topic
       set from ``jurisdiction_requirements`` via ``handbook_service``.
    4. Asks Gemini to grade coverage of each requirement against the
       extracted sections.
    5. Writes results to ``handbook_audit_reports``.

The audit is interactive — the frontend polls the report row every 2.5s
while the user waits — so it lives inline in the FastAPI process rather
than going through Celery. Same event loop as the route handler means we
reuse the app's settings, storage singleton, and asyncpg pool. The prior
Celery version had to bootstrap settings + open raw asyncpg connections
to dodge worker-loop lifecycle bugs; none of that is needed here.

Stalled audits (uvicorn restart mid-run, OOM, unhandled exception) leave
``status='processing'`` on the report row. The frontend surfaces a
"Audit appears stalled — Retry" banner after 5 minutes of no progress.
"""

import asyncio
import json
import logging
import os
from typing import Any, Optional

from app.database import get_connection
from app.core.services.model_json import strip_json_fence as _strip_json_fence

logger = logging.getLogger(__name__)

SECTION_EXTRACT_TIMEOUT = 180
GAP_CHECK_TIMEOUT = 120
MAX_REQUIREMENTS_PER_STATE = 24
MAX_SECTIONS_FOR_PROMPT = 80
SAMPLE_GAPS_COUNT = 2

_SEVERITY_RANK = {"critical": 0, "important": 1, "recommended": 2}


def _collapse_same_level_jurisdictions(
    requirements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """For each (category, rate_type, jurisdiction_level) group, keep ONE
    representative row and stash the rest under ``also_jurisdictions``.

    The handbook wizard preserves per-city rows on purpose (its output is
    a multi-jurisdiction addendum). The audit doesn't — Gemini grades the
    same topic once and the duplicates just become near-identical gaps.
    Rows with no ``category`` pass through unchanged.

    Representative selection within a group:
      1. Most recent ``effective_date`` (None sorts last).
      2. Tie-break: longest ``description``.
      3. Tie-break: input order (stable).

    Representative is a SHALLOW COPY with a new key ``also_jurisdictions``
    listing ``{name, level, source_url}`` for the dropped siblings (empty
    when group has one row). Caller's dicts are never mutated.
    """
    if not requirements:
        return []

    # Track group composition + insertion order so identical inputs
    # return identical outputs.
    groups: dict[tuple, list[dict[str, Any]]] = {}
    group_order: list[tuple] = []
    ungrouped_passthrough: list[dict[str, Any]] = []

    for req in requirements:
        category = (req.get("category") or "").strip().lower()
        if not category:
            ungrouped_passthrough.append(req)
            continue
        rate_type = req.get("rate_type")
        level = (req.get("jurisdiction_level") or "").strip().lower()
        key = (category, rate_type, level)
        if key not in groups:
            groups[key] = []
            group_order.append(key)
        groups[key].append(req)

    def _rank(req: dict[str, Any]) -> tuple:
        # Larger key wins under max(): present dates beat absent, newer
        # dates beat older, longer descriptions beat shorter.
        eff = req.get("effective_date")
        if eff is None:
            eff_key: tuple = (0,)
        else:
            try:
                eff_key = (1, eff.toordinal())
            except AttributeError:
                eff_key = (1, 0)
        desc_len = len(req.get("description") or "")
        return (eff_key, desc_len)

    result: list[dict[str, Any]] = []
    for key in group_order:
        rows = groups[key]
        if len(rows) == 1:
            rep = dict(rows[0])
            rep["also_jurisdictions"] = []
            result.append(rep)
            continue
        primary = max(rows, key=_rank)
        siblings = [r for r in rows if r is not primary]
        rep = dict(primary)
        rep["also_jurisdictions"] = [
            {
                "name": s.get("jurisdiction_name"),
                "level": s.get("jurisdiction_level"),
                "source_url": s.get("source_url"),
            }
            for s in siblings
        ]
        result.append(rep)

    # Ungrouped rows (no category) tacked on at end — preserves their
    # presence in the audit without grouping them.
    for req in ungrouped_passthrough:
        rep = dict(req)
        rep.setdefault("also_jurisdictions", [])
        result.append(rep)

    return result


def _merge_duplicate_gaps_for_state(
    state: str,
    gaps: list[dict[str, Any]],
    per_state: dict[str, int],
) -> list[dict[str, Any]]:
    """Bucket gaps by ``(state, requirement_key)``. On collision, MERGE
    rather than append: stash the secondary's ``requirement_title`` under
    primary.``also_covers`` and promote severity to the max of the group.

    Mutates ``per_state`` in place (decrements old severity, increments new
    severity, bumps ``covered`` for covered gaps). Returns the deduped
    list of uncovered gaps in first-seen order.

    Bucket excludes severity intentionally — rate-type-split rows can come
    back from Gemini with different severities, and bucketing on severity
    would let them slip past the merge.
    """
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []

    for gap in gaps:
        gap["state"] = state
        if gap.get("covered"):
            per_state["covered"] = per_state.get("covered", 0) + 1
            continue

        sev = (gap.get("severity") or "recommended").lower()
        if sev not in _SEVERITY_RANK:
            sev = "recommended"
        gap["severity"] = sev

        key = (state, gap.get("requirement_key") or gap.get("requirement_title") or "")
        existing = buckets.get(key)
        if existing is None:
            # Initialize merge-target fields with non-None lists so the
            # merge path can safely .append / iterate. setdefault alone
            # would leave a pre-existing None in place.
            if not isinstance(gap.get("also_covers"), list):
                gap["also_covers"] = []
            if not isinstance(gap.get("also_jurisdictions"), list):
                gap["also_jurisdictions"] = []
            per_state[sev] = per_state.get(sev, 0) + 1
            buckets[key] = gap
            order.append(key)
            continue

        # Merge into existing primary.
        if not isinstance(existing.get("also_covers"), list):
            existing["also_covers"] = []
        if not isinstance(existing.get("also_jurisdictions"), list):
            existing["also_jurisdictions"] = []

        new_title = (gap.get("requirement_title") or "").strip()
        if new_title:
            existing_titles_lower = {
                (existing.get("requirement_title") or "").strip().lower(),
                *((t or "").strip().lower() for t in existing["also_covers"]),
            }
            if new_title.lower() not in existing_titles_lower:
                existing["also_covers"].append(new_title)

        existing_jurisdictions = existing["also_jurisdictions"]
        existing_seen = {
            (j.get("name"), j.get("level"))
            for j in existing_jurisdictions
        }
        for j in gap.get("also_jurisdictions") or []:
            sig = (j.get("name"), j.get("level"))
            if sig not in existing_seen:
                existing_jurisdictions.append(j)
                existing_seen.add(sig)

        # Severity promotion: lower rank = higher severity.
        prev_sev = (existing.get("severity") or "recommended").lower()
        if _SEVERITY_RANK[sev] < _SEVERITY_RANK[prev_sev]:
            existing["severity"] = sev
            per_state[prev_sev] = max(per_state.get(prev_sev, 0) - 1, 0)
            per_state[sev] = per_state.get(sev, 0) + 1

    return [buckets[k] for k in order]


async def run_handbook_audit(report_id: str) -> None:
    """Public entry point — wraps ``_analyze`` with a top-level error
    handler that always writes ``status='failed'`` on uncaught exceptions
    so a buggy run can't leave the row stuck at 'processing'.
    """
    try:
        await _analyze(report_id)
    except Exception as exc:
        logger.exception("run_handbook_audit failed report_id=%s: %s", report_id, exc)
        try:
            await _mark_failed(report_id, str(exc))
        except Exception:
            logger.exception("Could not mark report failed: %s", report_id)


async def _analyze(report_id: str) -> None:
    async with get_connection() as conn:
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

    # Checkpoint sections so a Gemini failure on gap-grading doesn't lose
    # the section extraction work.
    async with get_connection() as conn:
        await conn.execute(
            """
            UPDATE handbook_audit_reports
            SET extracted_sections_jsonb = $2::jsonb
            WHERE id = $1
            """,
            report_id,
            json.dumps(sections),
        )

    from app.core.services.handbook_service import _fetch_state_requirements

    all_gaps: list[dict[str, Any]] = []
    state_summaries: dict[str, dict[str, int]] = {}

    for state in states:
        try:
            async with get_connection() as req_conn:
                req_map = await _fetch_state_requirements(
                    req_conn,
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

        # Pre-Gemini collapse: same-(category, rate_type, level) groups
        # become ONE prompt entry with siblings stashed on
        # also_jurisdictions. Drops near-identical gaps at the source so
        # the 24-row Gemini budget buys distinct topics.
        state_requirements = _collapse_same_level_jurisdictions(state_requirements)

        gaps = await _grade_state_coverage(
            state=state,
            industry=industry,
            requirements=state_requirements[:MAX_REQUIREMENTS_PER_STATE],
            sections=sections,
        )
        if gaps is None:
            logger.warning("Gap grading returned no result for %s", state)
            continue

        per_state = {"critical": 0, "important": 0, "recommended": 0, "covered": 0}
        gaps_for_state = _merge_duplicate_gaps_for_state(state, gaps, per_state)
        all_gaps.extend(gaps_for_state)
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

    async with get_connection() as conn:
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
    logger.info("handbook_audit ready report_id=%s gaps=%d", report_id, len(all_gaps))


async def _mark_failed(report_id: str, error_text: str) -> None:
    async with get_connection() as conn:
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
    """Build a google-genai client using the same env wiring as gemini_compliance.

    FastAPI's lifespan has already called ``load_settings()`` so a plain
    ``get_settings()`` works without the per-task fallback the old Celery
    version needed.
    """
    from google import genai
    from app.config import get_settings

    settings = get_settings()
    api_key = os.getenv("GEMINI_API_KEY") or settings.gemini_api_key
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")
    return genai.Client(api_key=api_key)




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
        try:
            pdf_part = types.Part(inline_data=types.Blob(mime_type="application/pdf", data=pdf_bytes))
        except Exception as exc:
            logger.exception("Could not build PDF Part: %s", exc)
            return []

    model_name = os.getenv("HANDBOOK_AUDIT_MODEL", "gemini-3-flash-preview")
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

    model_name = os.getenv("HANDBOOK_AUDIT_MODEL", "gemini-3-flash-preview")
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

    # Filter non-dict junk before pairing so index drift can't slip past.
    dict_results = [r for r in results if isinstance(r, dict)]
    if len(dict_results) != len(requirements):
        logger.warning(
            "Gap-grading length mismatch for %s: %d reqs vs %d results",
            state, len(requirements), len(dict_results),
        )

    cleaned: list[dict[str, Any]] = []
    for req, r in zip(requirements, dict_results):
        # Use the source category as the stable requirement_key — Gemini's
        # echo can drift in wording. Title falls back to req.title so an
        # empty Gemini title doesn't surface as a blank gap card.
        cleaned.append({
            "requirement_key": (req.get("category") or req.get("title") or "")[:120],
            "requirement_title": (r.get("requirement_title") or req.get("title") or "")[:240],
            "covered": bool(r.get("covered")),
            "severity": (r.get("severity") or "recommended").lower(),
            "citation": r.get("citation"),
            "what_good_looks_like": (r.get("what_good_looks_like") or "")[:600],
            "matched_section_title": r.get("matched_section_title"),
            "also_jurisdictions": req.get("also_jurisdictions") or [],
        })
    return cleaned
