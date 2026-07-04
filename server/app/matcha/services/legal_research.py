"""External legal research for Legal Pilot — CourtListener case search +
grounded-Gemini guidance synthesis.

Informational only, never legal advice: case-law hits are search-relevance
results, not vetted precedent, and the Gemini synthesis is a public-guidance
summary, not an assessment of the company's position. Only CourtListener API
rows become citable evidence (``case:<cluster_id>`` cids minted from rows
persisted here) — the Gemini guidance text is never cited, per
``legal_defense.validate_citations``'s index-membership invariant.
"""

import asyncio
import json
import logging
import re

import httpx
from google.genai import types

from app.config import get_settings
from app.core.services.genai_client import get_genai_client
from app.core.services.rate_limiter import get_rate_limiter
from app.database import get_connection

from .legal_defense import MODEL as _GEMINI_MODEL
from .legal_defense import _hum, _parse_json

logger = logging.getLogger(__name__)

COURTLISTENER_BASE = "https://www.courtlistener.com/api/rest/v4"
_CL_TIMEOUT = 20.0
_MAX_CASES = 8
_GUIDANCE_TIMEOUT = 90

# Copied from compliance_service._CODE_TO_STATE_NAME — kept local since this
# module only needs it to enrich the CourtListener query / Gemini prompt with
# a human-readable jurisdiction, not for any DB lookup.
_STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District Of Columbia",
}


_RESERVED_QUERY_CHARS_RE = re.compile(r'[\[\]{}()"~^:/&|]')


def _sanitize_query(query: str) -> str:
    """Neutralize CourtListener/Lucene query-syntax reserved characters that
    crash v4 search (500) or are rejected (400) — confirmed via direct
    probing of the live API. This is meant to be plain free-text keyword
    search; we never rely on CourtListener's operator syntax. Replaces with a
    space (never deletes, so word boundaries survive) then collapses
    whitespace. Pure, no I/O."""
    cleaned = _RESERVED_QUERY_CHARS_RE.sub(" ", query or "")
    return " ".join(cleaned.split())


def _parse_search_results(payload: dict, limit: int = _MAX_CASES) -> list[dict]:
    """Map CourtListener v4 ``type=o`` search results to compact case dicts.

    Pure, never raises — tolerates missing keys / an unexpected payload shape.
    """
    out: list[dict] = []
    try:
        results = (payload or {}).get("results") or []
    except AttributeError:
        return out
    for r in results[:limit]:
        try:
            if not isinstance(r, dict):
                continue
            cid = str(r.get("cluster_id") or r.get("id") or "")
            case_name = r.get("caseName") or r.get("caseNameFull") or ""
            if not cid or not case_name:
                continue
            citation = r.get("citation")
            citation = citation[0] if isinstance(citation, list) and citation else None
            opinions = r.get("opinions") or []
            snippet = r.get("snippet") or (
                opinions[0].get("snippet") if opinions and isinstance(opinions[0], dict) else None
            )
            out.append({
                "id": cid,
                "case_name": case_name,
                "citation": citation,
                "court": r.get("court") or "",
                "date_filed": r.get("dateFiled"),
                "url": "https://www.courtlistener.com" + (r.get("absolute_url") or ""),
                "snippet": snippet,
            })
        except Exception:  # noqa: BLE001 — one bad row never drops the rest
            continue
    return out


async def search_case_law(query: str, state: str | None = None, limit: int = _MAX_CASES) -> list[dict]:
    """GET CourtListener opinion search. Raises on transport/HTTP failure —
    callers isolate this (see ``run_research``)."""
    q = _sanitize_query(query)
    if state:
        state_name = _STATE_NAMES.get(state.upper())
        if state_name:
            q = f"{q} {state_name}"

    headers = {}
    token = get_settings().courtlistener_api_token
    if token:
        headers["Authorization"] = f"Token {token}"

    async with httpx.AsyncClient(timeout=_CL_TIMEOUT) as client:
        resp = await client.get(
            f"{COURTLISTENER_BASE}/search/",
            params={"q": q, "type": "o", "order_by": "score desc"},
            headers=headers,
        )
        resp.raise_for_status()
        return _parse_search_results(resp.json(), limit)


async def synthesize_guidance(matter: dict, juris_display: str | None, cases: list[dict]) -> dict:
    """Grounded-Gemini public-guidance briefing. Raises on failure — callers
    isolate this (see ``run_research``)."""
    label = _hum(matter.get("matter_type")) or "Employment matter"
    allegation = (matter.get("allegation") or "")[:300]
    case_names = ", ".join(c["case_name"] for c in cases[:5]) or "(none located)"

    prompt = (
        "You are compiling an INFORMATIONAL briefing of the public legal landscape "
        "for outside counsel. Matter type: " + label + ". Jurisdiction: "
        + (juris_display or "unspecified") + ". Allegation summary: " + allegation
        + ". Cases already located (do not re-verify): " + case_names
        + ". Using web search, summarize current federal and state agency guidance "
        "relevant to this matter type (EEOC enforcement guidance, DOL opinion letters, "
        "state agency rules), each with its source URL. Do NOT give legal advice, do NOT "
        "assess the company's position, do NOT invent case citations. Return STRICT JSON: "
        '{"summary": "<neutral 2-4 paragraph overview>", "key_authorities": '
        '[{"name","url","publisher","relevance"}]}'
    )

    rate_limiter = get_rate_limiter()
    await rate_limiter.check_limit("gemini_compliance", "legal_research")
    resp = await asyncio.wait_for(
        get_genai_client().aio.models.generate_content(
            model=_GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        ),
        timeout=_GUIDANCE_TIMEOUT,
    )
    await rate_limiter.record_call("gemini_compliance", "legal_research")

    data = _parse_json(getattr(resp, "text", "") or "")
    return {
        "summary": str(data.get("summary") or "").strip(),
        "key_authorities": [a for a in (data.get("key_authorities") or []) if isinstance(a, dict)],
    }


def parse_research_row(row: dict) -> dict:
    """asyncpg returns jsonb columns as raw text (no codec registered on the
    pool) — decode ``cases``/``guidance`` back into Python objects. Shared by
    every caller that reads ``legal_matter_research`` rows directly."""
    row = dict(row)
    for key in ("cases", "guidance"):
        v = row.get(key)
        if isinstance(v, str):
            try:
                row[key] = json.loads(v)
            except Exception:
                row[key] = None
    return row


async def _resolve_state(conn, matter: dict) -> str | None:
    """Location-first (company-scoped), then the explicit state override —
    the SAME precedence ``legal_defense.resolve_matter_jurisdiction`` applies,
    so the CourtListener search can never target a different state than the
    governing-law chain shown alongside it."""
    if matter.get("location_id"):
        loc = await conn.fetchrow(
            "SELECT state FROM business_locations WHERE id = $1 AND company_id = $2",
            matter["location_id"], matter["company_id"],
        )
        if loc and loc["state"]:
            return loc["state"].upper()
    return (matter.get("jurisdiction_state") or "").upper() or None


async def run_research(matter: dict, created_by, include_guidance: bool = True) -> dict:
    """Orchestrate one research run: persist a row, gather cases + (optionally)
    guidance, each isolated, finalize status. Never raises on partial failure —
    the row is only marked ``failed`` when nothing attempted succeeded (case
    search failed, and guidance either wasn't attempted or also failed).

    ``include_guidance=False`` skips the ~90s grounded-Gemini synthesis call
    entirely — just the CourtListener case search — for callers who only
    want a fast case-law refresh.

    Acquires its own short-lived pool connections around the DB phases so
    that NO pooled connection is held across the external CourtListener +
    Gemini calls (~110s worst case) — the same discipline the chat endpoint
    applies before its long Gemini call."""
    async with get_connection() as conn:
        state = await _resolve_state(conn, matter)
        allegation = (matter.get("allegation") or "")[:300]
        query = f"{_hum(matter.get('matter_type'))} {allegation}".strip()
        row = await conn.fetchrow(
            """INSERT INTO legal_matter_research
                   (matter_id, company_id, query, created_by, jurisdiction_state)
               VALUES ($1, $2, $3, $4, $5) RETURNING id""",
            matter["id"], matter["company_id"], query, created_by, state,
        )
        research_id = row["id"]

    cases: list[dict] = []
    case_err: str | None = None
    try:
        cases = await search_case_law(query, state=state)
    except Exception as e:  # noqa: BLE001 — isolation is the point
        logger.warning("legal_research: case search failed: %s", e)
        case_err = str(e)

    guidance: dict | None = None
    guid_err: str | None = None
    if include_guidance:
        try:
            juris_display = _STATE_NAMES.get(state) if state else None
            guidance = await synthesize_guidance(matter, juris_display, cases)
        except Exception as e:  # noqa: BLE001
            logger.warning("legal_research: guidance synthesis failed: %s", e)
            guid_err = str(e)

    async with get_connection() as conn:
        nothing_succeeded = bool(case_err) and (not include_guidance or bool(guid_err))
        if nothing_succeeded:
            error = f"Case search failed: {case_err}"
            if include_guidance:
                error += f"; guidance synthesis failed: {guid_err}"
            await conn.execute(
                "UPDATE legal_matter_research SET status='failed', error=$1, completed_at=NOW() WHERE id=$2",
                error, research_id,
            )
        else:
            error = None
            if case_err:
                error = f"Case search unavailable: {case_err}"
            elif include_guidance and guid_err:
                error = f"Guidance synthesis unavailable: {guid_err}"
            await conn.execute(
                """UPDATE legal_matter_research
                       SET status='complete', cases=$1::jsonb, guidance=$2::jsonb,
                           error=$3, completed_at=NOW()
                     WHERE id=$4""",
                json.dumps(cases), json.dumps(guidance) if guidance else None, error, research_id,
            )

        result = await conn.fetchrow("SELECT * FROM legal_matter_research WHERE id = $1", research_id)
    return parse_research_row(dict(result))
