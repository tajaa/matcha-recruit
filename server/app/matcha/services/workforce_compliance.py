"""Workforce compliance service — pay-transparency logic + EPL derive helpers.

Powers the business-facing trackers and feeds the broker EPL lens: when a tenant
has `workforce_compliance` on, three EPL factors (pay_transparency,
biometrics_bipa, ai_hiring_audit) derive from this data instead of being
broker-attested. Caller owns the asyncpg connection.
"""

from datetime import date, timedelta
from typing import Optional
from uuid import UUID

# States with salary-range / pay-scale posting (or on-request) laws as of 2026.
# Lightweight static list — not the heavy jurisdiction engine. Extend as laws change.
PAY_TRANSPARENCY_STATES = {
    "CA", "CO", "WA", "NY", "IL", "HI", "MN", "NJ", "VT", "DC", "MD", "CT", "NV", "RI",
}


def audit_dates(last_audit_date: Optional[date], cadence_days: int) -> tuple[Optional[date], bool]:
    """Compute (next_due_date, is_overdue) from a last-audit date + cadence."""
    if not last_audit_date:
        return None, True  # never audited → overdue
    nxt = last_audit_date + timedelta(days=cadence_days or 365)
    return nxt, nxt < date.today()


# --- pay transparency ------------------------------------------------------

async def _company_states(conn, company_id: UUID) -> set[str]:
    rows = await conn.fetch(
        "SELECT DISTINCT state FROM business_locations "
        "WHERE company_id = $1 AND state IS NOT NULL AND state <> '' AND COALESCE(is_active, true) = true",
        company_id,
    )
    return {r["state"].upper() for r in rows if r["state"]}


async def get_pay_transparency(conn, company_id: UUID) -> list[dict]:
    """Required states (constant ∩ the company's operating states) merged with
    stored status rows. Required states with no row default to 'action_needed'."""
    states = await _company_states(conn, company_id)
    required = sorted(states & PAY_TRANSPARENCY_STATES)
    stored = {
        r["state"]: r
        for r in await conn.fetch(
            "SELECT state, status, postings_include_ranges, note, updated_at "
            "FROM pay_transparency_status WHERE company_id = $1",
            company_id,
        )
    }
    out: list[dict] = []
    for st in required:
        r = stored.get(st)
        out.append({
            "state": st, "required": True,
            "status": r["status"] if r else "action_needed",
            "postings_include_ranges": r["postings_include_ranges"] if r else False,
            "note": r["note"] if r else None,
            "updated_at": r["updated_at"] if r else None,
        })
    # Any stored rows for non-required states (e.g. user added one manually).
    for st, r in stored.items():
        if st not in set(required):
            out.append({
                "state": st, "required": False, "status": r["status"],
                "postings_include_ranges": r["postings_include_ranges"],
                "note": r["note"], "updated_at": r["updated_at"],
            })
    return out


async def set_pay_transparency(conn, company_id: UUID, state: str, *, status: str,
                               postings_include_ranges: bool, note, updated_by) -> None:
    await conn.execute(
        """
        INSERT INTO pay_transparency_status
            (company_id, state, status, postings_include_ranges, note, updated_by, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, NOW())
        ON CONFLICT ON CONSTRAINT uq_pay_transparency_state DO UPDATE SET
            status = EXCLUDED.status, postings_include_ranges = EXCLUDED.postings_include_ranges,
            note = EXCLUDED.note, updated_by = EXCLUDED.updated_by, updated_at = NOW()
        """,
        company_id, state.upper()[:2], status, postings_include_ranges, note, updated_by,
    )


# --- EPL derive helpers (return (score, detail) or None to fall back to attestation) ---

async def derive_pay_transparency(conn, company_id: UUID) -> Optional[tuple[int, str]]:
    rows = await get_pay_transparency(conn, company_id)
    required = [r for r in rows if r["required"]]
    if not required:
        return 100, "No pay-transparency states in the company's footprint"
    compliant = sum(1 for r in required if r["status"] == "compliant")
    score = round(100 * compliant / len(required))
    return score, f"{compliant}/{len(required)} required states compliant"


async def derive_ai_audit(conn, company_id: UUID) -> Optional[tuple[int, str]]:
    row = await conn.fetchrow(
        "SELECT COUNT(*) AS total, "
        "COUNT(*) FILTER (WHERE next_due_date IS NULL OR next_due_date < CURRENT_DATE) AS overdue "
        "FROM hiring_ai_audits WHERE company_id = $1",
        company_id,
    )
    total = int(row["total"] or 0)
    if total == 0:
        return None  # nothing declared → fall back to broker attestation
    overdue = int(row["overdue"] or 0)
    current = total - overdue
    return round(100 * current / total), f"{current}/{total} AI tools audit-current"


async def derive_biometric(conn, company_id: UUID) -> Optional[tuple[int, str]]:
    rows = await conn.fetch(
        "SELECT is_active, consent_obtained FROM biometric_consent_points WHERE company_id = $1",
        company_id,
    )
    if not rows:
        return None  # nothing declared → fall back to broker attestation
    active = [r for r in rows if r["is_active"]]
    if not active:
        return 100, "No active biometric collection on file"
    consented = sum(1 for r in active if r["consent_obtained"])
    return round(100 * consented / len(active)), f"{consented}/{len(active)} collection points with consent"


async def derive_pay_equity(conn, company_id: UUID) -> Optional[tuple[int, str]]:
    """Score from the most recent pay-equity study: current & remediated → high,
    current but a sizeable unremediated gap → mid, overdue → low, none → fall back."""
    row = await conn.fetchrow(
        "SELECT review_date, gap_pct, remediation, "
        "(next_due_date IS NOT NULL AND next_due_date < CURRENT_DATE) AS overdue "
        "FROM pay_equity_reviews WHERE company_id = $1 "
        "ORDER BY review_date DESC NULLS LAST, created_at DESC LIMIT 1",
        company_id,
    )
    if not row:
        return None  # no study on file → fall back to broker attestation
    if row["overdue"]:
        return 40, f"Pay-equity study {row['review_date']} — overdue for refresh"
    gap = float(row["gap_pct"]) if row["gap_pct"] is not None else None
    if gap is not None and gap > 5 and not (row["remediation"] or "").strip():
        return 70, f"Pay-equity study current — {gap:.1f}% gap, remediation pending"
    return 100, f"Pay-equity study current ({row['review_date']})"
