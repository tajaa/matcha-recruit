"""Requirements backstop for the workforce-compliance page.

The workforce trackers (pay transparency / pay equity / biometric consent) are
things the business maintains about itself. This asks the reciprocal question:
of the jurisdiction requirements that actually APPLY to this company, which ones
does that self-maintained data leave it out of compliance with?

It reads the requirements CATALOG directly (`jurisdiction_requirements`), not the
per-tenant projection (`compliance_requirements`) — the projection only exists
where a compliance research run has already fired, and "what law applies to a CA
dental office" shouldn't depend on whether that job has run. Scoping mirrors the
tenant read path: the company's location states (+ federal), gated by industry
via the same `applicable_industries` overlap the catalog filter uses.

The compliant/gap decision is NOT redefined here — it calls the shared verdict
functions in `core.services.compliance_status`, the same rules the per-requirement
DERIVATIONS engine uses, so the workforce page and the compliance status table can
never disagree about whether a given control is satisfied. (AI hiring-tool / LL144
has no catalog regulation_key, so it has no backstop and is intentionally absent.)
"""
from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from ...core.services.compliance_service import _get_company_industry_tags
from ...core.services.compliance_status import (
    pay_transparency_verdict, pay_equity_verdict, biometrics_verdict,
)

# domain (matches the FE section) → catalog regulation_keys that back it.
DOMAIN_KEYS: Dict[str, tuple] = {
    "pay_transparency": ("pay_transparency",),
    "pay_equity": ("federal_equal_pay", "pay_equity"),
    "biometrics": ("state_biometric_privacy_laws",),
}

# Worst-first, so a domain's headline status is its worst requirement.
_SEVERITY = {"non_compliant": 0, "in_progress": 1, "unknown": 2, "compliant": 3}


async def compute_requirement_gate(conn, company_id: UUID, features: Dict[str, Any]) -> Dict[str, Any]:
    """Per-domain applicable requirements + whether the company's data satisfies each.

    Returns {domain: {"status": <worst>, "requirements": [{jurisdiction, title,
    status, reason, effective_date, source_url}]}}. Empty domains are omitted so
    the FE only renders a banner where a requirement actually applies.
    """
    if not features.get("workforce_compliance"):
        return {}

    tags = await _get_company_industry_tags(conn, company_id)
    states = {
        (r["state"] or "").upper()
        for r in await conn.fetch(
            "SELECT state FROM business_locations WHERE company_id = $1 AND COALESCE(is_active, true) = true",
            company_id,
        )
        if r["state"]
    }
    if not states:
        return {}

    # Workforce data the verdicts read — fetched once, not per requirement.
    pt_by_state = {
        (r["state"] or "").upper(): r["status"]
        for r in await conn.fetch(
            "SELECT state, status FROM pay_transparency_status WHERE company_id = $1", company_id,
        )
    }
    pe_review = await conn.fetchrow(
        """
        SELECT review_date, gap_pct, remediation,
               (next_due_date IS NOT NULL AND next_due_date < CURRENT_DATE) AS overdue
        FROM pay_equity_reviews WHERE company_id = $1
        ORDER BY review_date DESC NULLS LAST, created_at DESC LIMIT 1
        """,
        company_id,
    )
    bio = await conn.fetchrow(
        """
        SELECT COUNT(*) AS registered,
               COUNT(*) FILTER (WHERE consent_obtained IS NOT TRUE) AS missing_consent
        FROM biometric_consent_points
        WHERE company_id = $1 AND COALESCE(is_active, true) = true
        """,
        company_id,
    )
    registered = int(bio["registered"] or 0) if bio else 0
    missing = int(bio["missing_consent"] or 0) if bio else 0

    out: Dict[str, Any] = {}
    for domain, keys in DOMAIN_KEYS.items():
        reqs = await conn.fetch(
            """
            SELECT cat.title, cat.jurisdiction_name, cat.jurisdiction_level, cat.source_url,
                   cat.effective_date, cat.applicable_industries,
                   j.state AS j_state, j.level::text AS j_level
            FROM jurisdiction_requirements cat
            LEFT JOIN jurisdictions j ON j.id = cat.jurisdiction_id
            WHERE cat.regulation_key = ANY($1::text[])
              AND (j.country_code = 'US' OR j.country_code IS NULL)
              AND (UPPER(j.state) = ANY($2::text[]) OR j.level IN ('national', 'federal'))
              AND (cat.expiration_date IS NULL OR cat.expiration_date > CURRENT_DATE)
            ORDER BY j.level, cat.jurisdiction_name
            """,
            list(keys), list(states),
        )
        banners = []
        for r in reqs:
            # Industry gate — a healthcare-only requirement applies only to a
            # company whose tags intersect it (mirrors _filter_requirements_for_company).
            ind = r["applicable_industries"]
            if ind and not (set(ind) & tags):
                continue

            if domain == "pay_transparency":
                st = (r["j_state"] or "").upper()
                status, reason = pay_transparency_verdict(pt_by_state.get(st))
            elif domain == "pay_equity":
                status, reason = pay_equity_verdict(dict(pe_review) if pe_review else None)
            else:  # biometrics
                status, reason = biometrics_verdict(registered, missing)

            banners.append({
                "jurisdiction": r["jurisdiction_name"],
                "jurisdiction_level": r["jurisdiction_level"],
                "title": r["title"],
                "status": status,
                "reason": reason,
                "effective_date": str(r["effective_date"]) if r["effective_date"] else None,
                "source_url": r["source_url"],
            })

        if not banners:
            continue
        # Dedup identical (jurisdiction, title, status) rows the catalog may carry twice.
        seen, deduped = set(), []
        for b in banners:
            k = (b["jurisdiction"], b["title"], b["status"])
            if k in seen:
                continue
            seen.add(k)
            deduped.append(b)
        deduped.sort(key=lambda b: _SEVERITY.get(b["status"], 9))
        out[domain] = {"status": deduped[0]["status"], "requirements": deduped}

    return out
