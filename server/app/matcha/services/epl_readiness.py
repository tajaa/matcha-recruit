"""EPL-readiness scoring for the broker surface.

Employment Practices Liability (EPL) is priced by underwriters on exactly the HR
hygiene Matcha already manages (per WTW *Insurance Marketplace Realities 2026*,
pp. 84-87). This turns that operational data into an underwriting-grade
readiness score + an "what underwriters will ask" checklist the broker can take
to market.

Two kinds of factors:

- **Derived** — computed from Matcha data (policies, training, discipline, ER
  cases, multi-state compliance). No human input.
- **Attested** — the report's underwriting asks Matcha has no data source for
  (pay transparency, biometrics/BIPA, pay equity, AI-hiring audits, DEI). The
  broker records these during a consultative review; stored in
  ``company_epl_attestations``.

Composite = weighted sum of all factor sub-scores (0-100). Caller owns the conn.
"""

from typing import Any, Optional
from uuid import UUID

from app.core.feature_flags import merge_company_features

# Factor catalog. weight sums to 100 (derived 55 + attested 45). Order = display order.
FACTORS: list[dict[str, Any]] = [
    {"key": "anti_harassment_policy", "label": "Anti-harassment / EEO policy", "weight": 15, "kind": "derived"},
    {"key": "harassment_training",    "label": "Anti-harassment training",     "weight": 12, "kind": "derived"},
    {"key": "documented_discipline",  "label": "Documented progressive discipline", "weight": 10, "kind": "derived"},
    {"key": "er_case_management",     "label": "ER case management",           "weight": 8,  "kind": "derived"},
    {"key": "wage_hour_compliance",   "label": "Multi-state wage & hour compliance", "weight": 10, "kind": "derived"},
    {"key": "pay_transparency",       "label": "Pay-transparency compliance",  "weight": 9,  "kind": "attested"},
    {"key": "biometrics_bipa",        "label": "Biometric / BIPA controls",    "weight": 9,  "kind": "attested"},
    {"key": "pay_equity",             "label": "Pay-equity analysis",          "weight": 9,  "kind": "attested"},
    {"key": "ai_hiring_audit",        "label": "AI hiring-tool bias audit",    "weight": 9,  "kind": "attested"},
    {"key": "dei_posture",            "label": "DEI policy & posture",         "weight": 9,  "kind": "attested"},
]
ATTESTED_KEYS = {f["key"] for f in FACTORS if f["kind"] == "attested"}
ATTESTATION_STATUSES = ("in_place", "partial", "gap", "unknown")
_ATTEST_SCORE = {"in_place": 100, "partial": 50, "gap": 0, "unknown": 0}


def readiness_band(score: int) -> str:
    """Composite score → band. High score = EPL-ready (low exposure)."""
    if score >= 80:
        return "strong"
    if score >= 60:
        return "adequate"
    if score >= 35:
        return "developing"
    return "exposed"


def _factor_band(score: int) -> str:
    """Per-factor traffic-light for the checklist."""
    if score >= 70:
        return "strong"
    if score >= 35:
        return "partial"
    return "gap"


def _rate(num: int, den: int) -> float:
    return (num / den) if den else 0.0


async def _derived_scores(conn, company_id: UUID, features: dict) -> dict[str, dict]:
    """Compute the five data-derived factor sub-scores (each 0-100) + detail."""
    out: dict[str, dict] = {}

    # 1. Anti-harassment / EEO policy presence + signature rate (+ handbook).
    pol = await conn.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (WHERE active_ah) AS ah_count,
            COALESCE(SUM(signed) FILTER (WHERE active_ah), 0) AS ah_signed,
            COALESCE(SUM(total_sig) FILTER (WHERE active_ah), 0) AS ah_total
        FROM (
            SELECT
                (p.status = 'active' AND (
                    LOWER(COALESCE(p.category, '')) ~ '(harass|eeo|discrimination|conduct|equal)'
                    OR LOWER(p.title) ~ '(harass|eeo|discrimination|code of conduct|equal employ)'
                )) AS active_ah,
                COUNT(ps.id) FILTER (WHERE ps.status = 'signed') AS signed,
                COUNT(ps.id) AS total_sig
            FROM policies p
            LEFT JOIN policy_signatures ps ON ps.policy_id = p.id
            WHERE p.company_id = $1
            GROUP BY p.id, p.status, p.category, p.title
        ) sub
        """,
        company_id,
    )
    has_handbook = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM handbooks WHERE company_id = $1 AND status = 'active')",
        company_id,
    )
    ah_count = int(pol["ah_count"] or 0)
    sig_rate = _rate(int(pol["ah_signed"] or 0), int(pol["ah_total"] or 0))
    if ah_count > 0:
        score = round(60 + 40 * sig_rate)
        detail = f"{ah_count} anti-harassment/EEO polic{'y' if ah_count == 1 else 'ies'}, {round(sig_rate * 100)}% signed"
    elif has_handbook:
        score = 30
        detail = "Active handbook, but no distinct anti-harassment/EEO policy"
    else:
        score = 0
        detail = "No anti-harassment/EEO policy on file"
    out["anti_harassment_policy"] = {"score": score, "detail": detail}

    # 2. Anti-harassment training completion.
    tr = await conn.fetchrow(
        """
        SELECT COUNT(*) AS assigned,
               COUNT(*) FILTER (WHERE status = 'completed') AS completed
        FROM training_records
        WHERE company_id = $1
          AND (training_type = 'harassment_prevention'
               OR LOWER(title) ~ '(harass|discriminat|eeo)')
        """,
        company_id,
    )
    assigned = int(tr["assigned"] or 0)
    completed = int(tr["completed"] or 0)
    if assigned > 0:
        rate = _rate(completed, assigned)
        score = round(rate * 100)
        detail = f"{completed}/{assigned} completions ({round(rate * 100)}%)"
    else:
        score = 0
        detail = "No anti-harassment training" + ("" if features.get("training") else " (training not enabled)")
    out["harassment_training"] = {"score": score, "detail": detail}

    # 3. Documented progressive discipline (last 24mo, signed ratio).
    dis = await conn.fetchrow(
        """
        SELECT COUNT(*) AS cases,
               COUNT(*) FILTER (WHERE signature_status = 'signed') AS signed
        FROM progressive_discipline
        WHERE company_id = $1 AND issued_date >= CURRENT_DATE - INTERVAL '24 months'
        """,
        company_id,
    )
    d_cases = int(dis["cases"] or 0)
    if d_cases > 0:
        signed_ratio = _rate(int(dis["signed"] or 0), d_cases)
        score = round(50 + 50 * signed_ratio)
        detail = f"{d_cases} cases (24mo), {round(signed_ratio * 100)}% signed"
    else:
        score = 0
        detail = "No discipline records" + ("" if features.get("discipline") else " (discipline not enabled)")
    out["documented_discipline"] = {"score": score, "detail": detail}

    # 4. ER case management (last 24mo, resolution rate).
    er = await conn.fetchrow(
        """
        SELECT COUNT(*) AS cases,
               COUNT(*) FILTER (WHERE status = 'closed') AS closed
        FROM er_cases
        WHERE company_id = $1 AND created_at >= CURRENT_DATE - INTERVAL '24 months'
        """,
        company_id,
    )
    e_cases = int(er["cases"] or 0)
    if e_cases > 0:
        res_rate = _rate(int(er["closed"] or 0), e_cases)
        score = round(50 + 50 * res_rate)
        detail = f"{e_cases} ER cases (24mo), {round(res_rate * 100)}% resolved"
    else:
        score = 0
        detail = "No ER cases" + ("" if features.get("er_copilot") else " (ER Copilot not enabled)")
    out["er_case_management"] = {"score": score, "detail": detail}

    # 5. Multi-state wage & hour compliance coverage.
    wh = await conn.fetchrow(
        """
        SELECT
            COUNT(*) AS active_locations,
            COUNT(*) FILTER (WHERE wh.cnt > 0) AS covered_locations,
            COUNT(DISTINCT bl.state) AS state_count
        FROM business_locations bl
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS cnt FROM compliance_requirements cr
            WHERE cr.location_id = bl.id
              AND cr.category IN ('minimum_wage','overtime','pay_frequency','meal_break',
                                  'rest_break','paid_sick_leave','final_pay')
              AND (cr.expiration_date IS NULL OR cr.expiration_date > CURRENT_DATE)
        ) wh ON true
        WHERE bl.company_id = $1 AND COALESCE(bl.is_active, true) = true
        """,
        company_id,
    )
    active_loc = int(wh["active_locations"] or 0)
    covered = int(wh["covered_locations"] or 0)
    states = int(wh["state_count"] or 0)
    if active_loc > 0:
        score = round(100 * _rate(covered, active_loc))
        detail = f"{covered}/{active_loc} locations covered across {states} state{'' if states == 1 else 's'}"
    else:
        score = 0
        detail = "No business locations on file"
    out["wage_hour_compliance"] = {"score": score, "detail": detail}

    return out


def _serialize_attestation(r) -> dict:
    return {
        "item_key": r["item_key"],
        "status": r["status"],
        "note": r["note"],
        "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
    }


async def get_attestations(conn, company_id: UUID) -> dict[str, dict]:
    """item_key → attestation row for a company."""
    rows = await conn.fetch(
        "SELECT item_key, status, note, updated_at FROM company_epl_attestations WHERE company_id = $1",
        company_id,
    )
    return {r["item_key"]: _serialize_attestation(r) for r in rows}


async def compute_epl_readiness(conn, company_id: UUID) -> dict:
    """Full EPL-readiness assessment for one company: composite + per-factor breakdown."""
    company = await conn.fetchrow(
        "SELECT enabled_features, signup_source FROM companies WHERE id = $1", company_id
    )
    features = merge_company_features(
        company["enabled_features"] if company else None,
        signup_source=company["signup_source"] if company else None,
    )

    derived = await _derived_scores(conn, company_id, features)
    attestations = await get_attestations(conn, company_id)

    # Workforce-Compliance flip: when the BUSINESS tracks these directly (feature
    # on + data declared), the 3 normally-attested factors derive from that data.
    # A None result falls back to the broker attestation (today's behavior).
    wf_derived: dict = {}
    if features.get("workforce_compliance"):
        from . import workforce_compliance as wf
        for key, fn in (
            ("pay_transparency", wf.derive_pay_transparency),
            ("ai_hiring_audit", wf.derive_ai_audit),
            ("biometrics_bipa", wf.derive_biometric),
        ):
            res = await fn(conn, company_id)
            if res is not None:
                wf_derived[key] = res  # (score, detail)

    factors: list[dict] = []
    composite = 0.0
    derived_total = attested_total = 0.0
    derived_max = attested_max = 0.0
    for f in FACTORS:
        key = f["key"]
        if f["kind"] == "derived":
            sub, detail, att, actual = derived[key]["score"], derived[key]["detail"], None, "derived"
        elif key in wf_derived:
            sub, detail, att, actual = wf_derived[key][0], wf_derived[key][1], None, "derived"
        else:
            a = attestations.get(key)
            status = a["status"] if a else "unknown"
            sub = _ATTEST_SCORE.get(status, 0)
            detail = {
                "in_place": "Attested: in place", "partial": "Attested: partial",
                "gap": "Attested: gap", "unknown": "Not yet reviewed",
            }[status]
            att = a or {"item_key": key, "status": "unknown", "note": None, "updated_at": None}
            actual = "attested"
        contribution = f["weight"] * sub / 100.0
        composite += contribution
        if actual == "derived":
            derived_total += contribution
            derived_max += f["weight"]
        else:
            attested_total += contribution
            attested_max += f["weight"]
        factors.append({
            "key": key, "label": f["label"], "kind": actual, "weight": f["weight"],
            "score": sub, "status": _factor_band(sub), "contribution": round(contribution, 1),
            "detail": detail, "attestation": att,
        })

    score = round(composite)
    return {
        "company_id": str(company_id),
        "score": score,
        "band": readiness_band(score),
        "derived_score": round(derived_total),
        "attested_score": round(attested_total),
        "derived_max": round(derived_max),
        "attested_max": round(attested_max),
        "factors": factors,
    }


def assess_from_statuses(statuses: dict) -> dict:
    """EPL assessment where EVERY factor is a broker-attested status.

    For off-platform clients (no Matcha data to derive from). Reuses the same
    factor catalog, weights, and bands as the tenant path so scores are
    directly comparable. ``statuses`` maps item_key -> status; missing factors
    default to 'unknown'.
    """
    factors: list[dict] = []
    composite = 0.0
    for f in FACTORS:
        status = statuses.get(f["key"]) or "unknown"
        if status not in ATTESTATION_STATUSES:
            status = "unknown"
        sub = _ATTEST_SCORE.get(status, 0)
        contribution = f["weight"] * sub / 100.0
        composite += contribution
        factors.append({
            "key": f["key"],
            "label": f["label"],
            "kind": f["kind"],
            "weight": f["weight"],
            "score": sub,
            "status": _factor_band(sub),
            "contribution": round(contribution, 1),
            "attest_status": status,
        })
    score = round(composite)
    # Off-platform = fully attested → no derived portion.
    return {"score": score, "band": readiness_band(score),
            "derived_max": 0, "attested_max": 100, "factors": factors}


def top_gap(assessment: dict) -> Optional[dict]:
    """The factor losing the most points (weight × shortfall) — the headline gap."""
    worst = None
    worst_loss = -1.0
    for f in assessment["factors"]:
        loss = f["weight"] * (100 - f["score"]) / 100.0
        if loss > worst_loss:
            worst_loss = loss
            worst = f
    if not worst or worst["score"] >= 70:
        return None
    return {"key": worst["key"], "label": worst["label"], "score": worst["score"]}
