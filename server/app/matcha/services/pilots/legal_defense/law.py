"""Matter-scoped external legal context — governing requirements, pending
legislation, and externally-researched case law."""

import logging
import time

from app.config import get_settings

from ._shared import _dt_date, _hum
from .theory import _BROAD, _Topic

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Matter-scoped external legal context — jurisdiction, governing requirements,
# pending legislation, and externally-researched case law. Only populated
# when the matter carries a location/state (see resolve_matter_jurisdiction).
# --------------------------------------------------------------------------- #
async def _gather_law(conn, matter: dict, juris: dict, topic: _Topic = _BROAD) -> tuple[dict | None, dict | None]:
    """Governing requirements + pending legislation for the matter's
    jurisdiction chain, filtered to the matter theory's relevant categories
    when possible. Returns ``(law_source, legislation_source)``, each shaped
    like an existing evidence source (``{"label", "records"}``) or None.

    Takes the same ``topic`` the record sources are filtered by, so the
    governing law and the company records can never describe different
    theories of the same case."""
    jurisdiction_ids = [c["id"] for c in juris["chain"]]
    # NOT ``or None`` — an empty allowlist means "no jurisdiction category is
    # relevant to this theory", the same as it does for the record sources.
    # Collapsing it to None would pull the ENTIRE jurisdiction corpus, the exact
    # law/record divergence the shared ``topic`` was introduced to prevent.
    categories = topic.compliance
    rows = None

    if get_settings().gemini_api_key and matter.get("allegation"):
        try:
            from app.core.services.compliance_rag import ComplianceRAGService
            from app.core.services.embedding_service import EmbeddingService

            es = EmbeddingService(api_key=get_settings().gemini_api_key)
            rag = ComplianceRAGService(es)
            query = f"{matter.get('allegation') or ''} {_hum(matter.get('matter_type'))}"
            hits = await rag.search_requirements(
                query=query, conn=conn, jurisdiction_ids=jurisdiction_ids,
                categories=categories, top_k=30, min_similarity=0.25,
                statuses=["active"],  # repealed/superseded law must not read as current
            )
            if hits:
                rows = [{
                    "requirement_id": h["requirement_id"], "title": h["title"],
                    "category": h["category"], "current_value": h.get("current_value"),
                    "statute_citation": h.get("statute_citation"),
                    "effective_date": h.get("effective_date"),
                    "jurisdiction_level": h.get("jurisdiction_level"),
                    "jurisdiction_name": h.get("jurisdiction_name"),
                } for h in hits]
        except Exception as e:  # noqa: BLE001 — fall through to direct query
            logger.warning("legal_defense: RAG law retrieval unavailable: %s", e)

    if rows is None:
        async def _fetch(cats):
            return await conn.fetch(
                """
                SELECT id, title, category, current_value, statute_citation, effective_date,
                       jurisdiction_level, jurisdiction_name
                FROM jurisdiction_requirements
                WHERE jurisdiction_id = ANY($1::uuid[]) AND status = 'active'
                  AND ($2::text[] IS NULL OR category = ANY($2))
                ORDER BY effective_date DESC NULLS LAST LIMIT 40
                """,
                jurisdiction_ids, cats,
            )

        rows = await _fetch(categories)
        if not rows and categories:
            # A theory whose categories this jurisdiction happens not to track
            # must not blank the source entirely — widen to the full
            # jurisdiction. An EMPTY list is not "no categories tracked", it is
            # "no category is relevant", so it never widens.
            rows = await _fetch(None)
        rows = [dict(r) for r in rows]

    law_records = [{
        "cid": f"law:{r['requirement_id'] if 'requirement_id' in r else r['id']}",
        "ref": r.get("statute_citation") or _hum(r["category"]),
        "summary": f"{r['title']}"
                   + (f" = {r['current_value']}" if r.get("current_value") else "")
                   + f" ({r.get('jurisdiction_name') or ''}, {_hum(r.get('jurisdiction_level'))})",
        "when": _dt_date(r.get("effective_date")),
    } for r in rows]
    law_source = {"label": "Governing requirements (jurisdiction)", "records": law_records} if law_records else None

    bill_rows = await conn.fetch(
        """
        SELECT id, title, category, current_status, expected_effective_date, impact_summary
        FROM jurisdiction_legislation
        WHERE jurisdiction_id = ANY($1::uuid[])
        ORDER BY expected_effective_date ASC NULLS LAST LIMIT 15
        """,
        jurisdiction_ids,
    )
    bill_records = [{
        "cid": f"bill:{r['id']}",
        "ref": _hum(r["category"]) or "Legislation",
        "summary": f"{r['title']} — {_hum(r['current_status'])}"
                   + (f": {r['impact_summary'][:160]}" if r["impact_summary"] else ""),
        "when": _dt_date(r["expected_effective_date"]),
    } for r in bill_rows]
    bill_source = {"label": "Pending legislation (jurisdiction)", "records": bill_records} if bill_records else None

    return law_source, bill_source


# The law/legislation lookup costs a Gemini embedding round-trip (RAG path)
# plus several queries, and gather_evidence runs on EVERY chat turn while the
# route holds a pooled connection. A matter's governing law doesn't change
# turn-to-turn, so cache per (matter, jurisdiction, type, allegation) with a
# short TTL. Bounded; whole-cache clear on overflow is fine at this size.
_LAW_CACHE: dict = {}
_LAW_CACHE_TTL = 300.0
_LAW_CACHE_MAX = 256


async def _gather_law_cached(conn, matter: dict, juris: dict, topic: _Topic = _BROAD) -> tuple[dict | None, dict | None]:
    key = (
        str(matter.get("id")),
        str(juris.get("jurisdiction_id")),
        matter.get("matter_type"),
        matter.get("allegation") or "",
        topic.label,
    )
    hit = _LAW_CACHE.get(key)
    if hit and time.monotonic() - hit[0] < _LAW_CACHE_TTL:
        return hit[1], hit[2]
    law_src, bill_src = await _gather_law(conn, matter, juris, topic)
    if len(_LAW_CACHE) >= _LAW_CACHE_MAX:
        _LAW_CACHE.clear()
    _LAW_CACHE[key] = (time.monotonic(), law_src, bill_src)
    return law_src, bill_src


async def _gather_case_law(conn, matter_id, state: str | None = None,
                           theory: str | None = None) -> dict | None:
    """Externally-researched case law from the most recent completed
    ``legal_matter_research`` run (see ``services/legal_research.py``).
    ``case:`` cids are minted only from these persisted CourtListener API
    rows — never from model text.

    A run must match the matter's CURRENT scope on both axes to be served.
    ``state``: a matter whose location was corrected after research ran must not
    pair the new jurisdiction's governing law with the old state's case law.
    ``theory``: likewise for subject — a run made under another theory (or, for
    rows predating the column, under none at all, when the search had no subject
    anchor and could return an in-state case about anything) is stale for a
    themed matter. Both degrade to "no case law" until research is re-run, which
    is the honest answer; a broad matter still accepts any run, as it always has."""
    from ..legal_research import parse_research_row  # lazy: legal_research imports from this package

    row = await conn.fetchrow(
        """SELECT cases, guidance, jurisdiction_state FROM legal_matter_research
             WHERE matter_id = $1 AND status = 'complete' AND cases IS NOT NULL
               AND ($2::varchar IS NULL OR jurisdiction_state IS NULL OR jurisdiction_state = $2)
               AND ($3::varchar IS NULL OR theory = $3)
             ORDER BY created_at DESC LIMIT 1""",
        matter_id, state, theory,
    )
    if not row or not row["cases"]:
        return None
    cases = parse_research_row(dict(row)).get("cases")
    if not isinstance(cases, list):
        return None
    records = [{
        "cid": f"case:{c['id']}",
        "ref": c.get("citation") or c.get("court") or "opinion",
        "summary": f"{c['case_name']} — {c.get('court') or ''}",
        "when": c.get("date_filed") or "",
    } for c in cases if isinstance(c, dict) and c.get("id") and c.get("case_name")]
    if not records:
        return None
    return {"label": "Case law (external research — informational)", "records": records}
