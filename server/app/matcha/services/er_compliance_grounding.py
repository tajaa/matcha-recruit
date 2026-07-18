"""ER Copilot compliance grounding — jurisdiction-statute corpus for case AI.

ER guidance and outcome analysis advise on the most law-dense, highest-liability
decisions a tenant makes (terminations, complaints, investigations) but today do
so from case facts + the company's own policies only — no statutory grounding.
This module resolves the case's jurisdiction(s) and builds a *cited* corpus of
state employment-law requirements from the shared `jurisdiction_requirements`
catalog, so the analyzer can ground a recommendation in (e.g.) a final-pay or
retaliation statute and the shared `legal_defense.validate_citations` gate can
drop anything it invents.

Design mirrors `discipline_ai.build_draft_corpus`: the rendered prompt corpus
and the flat cid→record index are built together, so nothing is citable-but-
unshown. cid scheme (flat): ``jur:<requirement_id>``.

Deliberately does NOT reuse `handbook_service._fetch_state_requirements` — that
SELECT returns neither the row id (needed for a stable cid) nor the
`statute_citation` (needed for the chip), and reusing it would force an edit to
a function handbook generation shares. This owns a small, dedicated query
instead. The read is codified-gated (`codified_gate_sql`) to match every other
tenant-facing "this is the law you must follow" surface.

Empty in → empty out: no jurisdiction, no codified rows, or any failure yields
``("", {})`` and the caller behaves exactly as it does today (no citations, no
"grounding" section). The feature is a strict superset of current behavior.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Employment-relations categories worth pulling for an ER matter. Every slug here
# is a REAL catalog category key (`compliance_registry.py:CATEGORY_KEYS`) — an
# invented slug (e.g. "termination", "retaliation", "harassment_prevention") is a
# regulation key or nothing at all and would silently match zero rows while
# hiding the real ones. Kept small to protect the prompt budget; filtered in SQL.
ER_RELEVANT_CATEGORIES: frozenset[str] = frozenset({
    "final_pay",
    "pay_frequency",
    "equal_pay",
    "pay_transparency",
    "anti_discrimination",
    "whistleblower",
    "leave",
    "sick_leave",
    "background_checks",
})

_MAX_ROWS = 25
_DESC_CAP = 400


async def _resolve_states(conn, company_id, involved_employee_ids: list[str]) -> list[str]:
    """States for the case: the involved employees' work_state, else company-wide.

    Employee rows are tenant-scoped on `org_id` (== the company id), which also
    defends against a case carrying an employee id from another tenant.
    """
    states: set[str] = set()
    ids = [str(i) for i in (involved_employee_ids or []) if i]
    if ids:
        try:
            rows = await conn.fetch(
                """
                SELECT DISTINCT work_state
                FROM employees
                WHERE id::text = ANY($1::text[])
                  AND org_id::text = $2::text
                  AND work_state IS NOT NULL
                """,
                ids,
                str(company_id),
            )
            states = {(r["work_state"] or "").strip().upper() for r in rows if r["work_state"]}
        except Exception:
            logger.exception("er_grounding: involved-employee state resolution failed")

    if not states:
        # Fallback: every active employee's work location (same corpus the other
        # grounded features scope on).
        try:
            from app.core.services import handbook_service

            scopes = await handbook_service.derive_handbook_scopes_from_employees(
                conn, str(company_id)
            )
            states = {
                (s.get("state") or "").strip().upper()
                for s in scopes
                if s.get("state")
            }
        except Exception:
            logger.exception("er_grounding: company-scope fallback failed")

    if not states:
        # Final fallback: the company's own business locations — the SAME signal
        # the /compliance page keys off. A tenant with no employee roster (or
        # employees lacking work_state) still operates in known states; without
        # this, ER grounding reads empty while /compliance is rich for the exact
        # same company.
        try:
            rows = await conn.fetch(
                """
                SELECT DISTINCT state
                FROM business_locations
                WHERE company_id::text = $1::text
                  AND COALESCE(is_active, true) = true
                  AND state IS NOT NULL
                """,
                str(company_id),
            )
            states = {(r["state"] or "").strip().upper() for r in rows if r["state"]}
        except Exception:
            logger.exception("er_grounding: business-location fallback failed")

    return sorted(s for s in states if s)


async def build_jurisdiction_corpus(
    conn,
    company_id,
    involved_employee_ids: list[str],
) -> tuple[str, dict[str, dict[str, Any]]]:
    """Return ``(corpus_text, index)`` of codified employment-law requirements.

    ``index`` maps ``jur:<id>`` → the record dict. Both are empty when nothing
    resolves — callers treat that as "grounding unavailable" and are unchanged.
    """
    states = await _resolve_states(conn, company_id, involved_employee_ids)
    if not states:
        return "", {}
    # Federal employment law lives on the jurisdiction keyed state='US' (never a
    # value of employees.work_state), so it must be added explicitly or the whole
    # federal slice — the bulk of the codified corpus — is excluded.
    states_with_federal = sorted(set(states) | {"US"})

    try:
        from app.core.services.compliance_service import codified_gate_sql

        gate = await codified_gate_sql("jr", conn=conn)
        rows = await conn.fetch(
            f"""
            SELECT jr.id, j.state, jr.category, jr.title, jr.description,
                   jr.current_value, jr.statute_citation, jr.source_url,
                   jr.effective_date
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE j.state = ANY($1::varchar[])
              AND jr.status = 'active'
              AND (jr.expiration_date IS NULL OR jr.expiration_date >= CURRENT_DATE)
              AND jr.category = ANY($2::varchar[])
              {gate}
            ORDER BY (j.state = 'US') ASC,  -- state-specific first, federal after
                     j.state,
                     COALESCE(jr.effective_date, CURRENT_DATE) DESC,
                     COALESCE(jr.updated_at, jr.created_at) DESC
            LIMIT $3
            """,
            states_with_federal,
            list(ER_RELEVANT_CATEGORIES),
            _MAX_ROWS,
        )
    except Exception:
        logger.exception("er_grounding: requirement fetch failed")
        return "", {}

    chosen = [dict(r) for r in rows]
    if not chosen:
        return "", {}

    index: dict[str, dict[str, Any]] = {}
    lines: list[str] = []
    for r in chosen:
        cid = f"jur:{r['id']}"
        state = (r.get("state") or "").strip().upper()
        category = (r.get("category") or "").strip()
        title = (r.get("title") or "Requirement").strip()
        desc = (r.get("description") or r.get("current_value") or "").strip()
        if len(desc) > _DESC_CAP:
            desc = desc[:_DESC_CAP].rstrip() + "…"
        citation = (r.get("statute_citation") or "").strip()
        index[cid] = {
            "cid": cid,
            "requirement_id": str(r["id"]),
            "state": state,
            "category": category,
            "title": title,
            # What the law actually requires. Kept on the row (not only in the
            # corpus TEXT below) so a consumer that grounds off the index alone
            # still gets the obligation, not just its title — citing a real cid
            # while inventing its content is the one hallucination
            # `validate_citations` cannot catch.
            "description": desc,
            "statute_citation": citation or None,
            "source_url": r.get("source_url") or None,
        }
        cite_str = citation or "uncited"
        lines.append(f"[{cid}] ({state} — {category}) {title}: {desc} Citation: {cite_str}")

    return "\n".join(lines), index


def build_citation_records(
    clean_map: list[dict], index: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Distinct cited requirements, in first-cited order → citation dicts.

    Pure. Only ids present in ``index`` survive (the map is already gated, but we
    never trust an id we can't render)."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in clean_map or []:
        for cid in item.get("cited_ids") or []:
            if cid in seen or cid not in index:
                continue
            seen.add(cid)
            out.append(index[cid])
    return out
