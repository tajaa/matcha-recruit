"""Per-requirement compliance status — does this tenant actually obey this law?

The catalog says what is required. Until now nothing said whether the business
complies, so every downstream number was a statutory CEILING wearing a risk
costume: `compliance_risk` summed penalty ranges over four narrow issue sources
(and `_wage_penalty_for_location` is hardcoded to `category = 'minimum_wage'`),
while `risk_index._compliance_component` — 25% of the composite a BROKER reads —
scored "share of locations with >=1 non-expired requirement row", i.e. whether we
had researched their law at all. A company violating everything scored 100/100.

This module produces the missing fact, and the invariants are all about not
overclaiming it:

**Three ways to know, and they are not equal.** `derived` means the system
compared facts it already holds (this employee's pay rate against this
jurisdiction's floor). `attested` means a human said so. `unknown` means we do
not know — and `unknown` NEVER scores as compliant. That is the evals' rule
("unmeasured is null, never 100") applied where money is attached: scoring a
blind spot as clean is how a broker hands an underwriter a number that
understates the book.

**Derived beats attested — but only when derived has an answer.** A deterministic
fact outranks an opinion (the discipline-gate precedent). The displaced
attestation is preserved in `evidence.superseded_attestation` rather than
deleted, and the flip is audit-logged: "we said we were compliant, the payroll
data disagrees" is exactly the trail an ER case needs.

**A feature we cannot see through is a blind spot, not a violation.** If
`training` is off we hold no training records, so absence of evidence is not
evidence of non-compliance — the derivation returns None and the status stays
`unknown`. This mirrors `epl_readiness._gated_assessed`. Getting this wrong would
manufacture violations out of unsold features.

Status is keyed on the CATALOG row (`jurisdiction_requirement_id`), never the
projection: projection rows are rewritten on every check and churn (a live run
watched a location go 22 -> 17 codified rows between two checks), while the
catalog id is stable. See migration `reqstatus01`.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from uuid import UUID

logger = logging.getLogger(__name__)

STATUSES = ("compliant", "non_compliant", "in_progress", "unknown")
BASES = ("derived", "attested")

# A derivation returns (status, evidence) when it can decide, or None when it
# cannot see — never a guess.
DerivationResult = Optional[Tuple[str, Dict[str, Any]]]


@dataclass(frozen=True)
class Derivation:
    """One regulation_key the system can judge from data it already holds.

    ``required_feature`` marks a derivation whose evidence only exists when the
    tenant bought the feature. Without it the derivation is blind and must return
    None (-> unknown), never `compliant` (we'd be certifying an unmeasured thing)
    and never `non_compliant` (we'd be inventing a violation from an unsold
    feature).
    """
    key: str
    fn: Callable[..., Awaitable[DerivationResult]]
    label: str
    required_feature: Optional[str] = None


# ── pure rules (unit-tested, no DB) ─────────────────────────────────────────

def resolve_status(
    derived: DerivationResult,
    attested: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Optional[str], Dict[str, Any]]:
    """(status, basis, evidence) from a derivation result + any attestation.

    Precedence: a derivation that reached an answer wins; otherwise the
    attestation stands; otherwise unknown. The loser is never discarded silently
    — a superseded attestation rides along in the evidence so the disagreement
    stays visible.
    """
    if derived is not None:
        status, evidence = derived
        evidence = dict(evidence or {})
        if attested and attested.get("status") and attested["status"] != status:
            evidence["superseded_attestation"] = {
                "status": attested.get("status"),
                "note": attested.get("note"),
                "at": attested.get("at"),
            }
        return status, "derived", evidence

    if attested and attested.get("status"):
        return attested["status"], "attested", {"note": attested.get("note")}

    return "unknown", None, {}


def rollup(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Coverage + posture counts over status rows. Pure.

    `known` deliberately excludes `unknown`: the point of the number is to admit
    how much of the obligation surface we have not measured.
    """
    total = len(rows)
    by_status = {s: 0 for s in STATUSES}
    derived = attested = 0
    for r in rows:
        st = r.get("status") or "unknown"
        by_status[st] = by_status.get(st, 0) + 1
        if r.get("basis") == "derived":
            derived += 1
        elif r.get("basis") == "attested":
            attested += 1
    known = total - by_status["unknown"]
    return {
        "total": total,
        "known": known,
        "coverage_pct": round(100 * known / total) if total else None,
        "derived": derived,
        "attested": attested,
        **{f"count_{s}": by_status[s] for s in STATUSES},
    }


# ── derivations ─────────────────────────────────────────────────────────────

async def _derive_minimum_wage(
    conn, *, company_id: UUID, location_id: UUID, row: Dict[str, Any], ctx: Dict[str, Any]
) -> DerivationResult:
    """Hourly pay rates at this location against the jurisdiction's floor.

    The one in/out signal that already existed in the product (compliance_service
    `_violation_count_for_row`), lifted here so it is one derivation among many
    rather than the only thing the risk engine can see.
    """
    threshold = row.get("numeric_value")
    if threshold is None:
        return None
    emps = [e for e in ctx["employees"].get(location_id, [])
            if (e["pay_classification"] or "").lower() == "hourly" and e["pay_rate"] is not None]
    if not emps:
        return None  # No hourly staff here: nothing to compare, not "compliant".
    under = [e for e in emps if float(e["pay_rate"]) < float(threshold)]
    if under:
        return "non_compliant", {
            "rule": "hourly pay below the jurisdiction floor",
            "threshold": float(threshold),
            "violations": len(under),
            "employees_checked": len(emps),
            "examples": [
                {"name": f"{e['first_name']} {e['last_name']}".strip(), "pay_rate": float(e["pay_rate"])}
                for e in under[:5]
            ],
        }
    return "compliant", {
        "rule": "hourly pay at or above the jurisdiction floor",
        "threshold": float(threshold),
        "employees_checked": len(emps),
    }


async def _derive_exempt_salary(
    conn, *, company_id: UUID, location_id: UUID, row: Dict[str, Any], ctx: Dict[str, Any]
) -> DerivationResult:
    """Exempt salaries against the exemption threshold.

    `pay_rate` for an exempt employee is an ANNUAL salary in this schema, while
    for hourly it is an hourly rate — the column is polymorphic on
    pay_classification, so the two derivations must not share a comparison.
    """
    threshold = row.get("numeric_value")
    if threshold is None:
        return None
    emps = [e for e in ctx["employees"].get(location_id, [])
            if (e["pay_classification"] or "").lower() == "exempt" and e["pay_rate"] is not None]
    if not emps:
        return None
    under = [e for e in emps if float(e["pay_rate"]) < float(threshold)]
    if under:
        return "non_compliant", {
            "rule": "exempt salary below the exemption threshold",
            "threshold": float(threshold),
            "violations": len(under),
            "employees_checked": len(emps),
            "examples": [
                {"name": f"{e['first_name']} {e['last_name']}".strip(), "salary": float(e["pay_rate"])}
                for e in under[:5]
            ],
        }
    return "compliant", {
        "rule": "exempt salaries at or above the exemption threshold",
        "threshold": float(threshold),
        "employees_checked": len(emps),
    }


async def _derive_harassment_training(
    conn, *, company_id: UUID, location_id: UUID, row: Dict[str, Any], ctx: Dict[str, Any]
) -> DerivationResult:
    """Anti-harassment training completion. Same corpus as epl_readiness's
    harassment_training factor — one source of truth for "did they train"."""
    tr = ctx.get("training")
    if tr is None or int(tr["assigned"] or 0) == 0:
        return None  # Nothing assigned: we cannot tell trained-and-unrecorded
        # from untrained. Blind, not violating.
    assigned, completed = int(tr["assigned"]), int(tr["completed"] or 0)
    if completed < assigned:
        return "in_progress", {
            "rule": "anti-harassment training assigned but incomplete",
            "completed": completed, "assigned": assigned,
        }
    return "compliant", {
        "rule": "anti-harassment training complete",
        "completed": completed, "assigned": assigned,
    }


async def _derive_injury_recordkeeping(
    conn, *, company_id: UUID, location_id: UUID, row: Dict[str, Any], ctx: Dict[str, Any]
) -> DerivationResult:
    """OSHA recordability decided on this location's recordable-eligible incidents.

    An incident left unclassified past its window is the documented failure mode
    the ir_deadline_alerts worker already chases; here it becomes a status.
    """
    inc = ctx["incidents"].get(location_id)
    if not inc or int(inc["total"] or 0) == 0:
        return None  # No incidents: nothing to record, not proof of a system.
    unclassified = int(inc["unclassified"] or 0)
    if unclassified:
        return "non_compliant", {
            "rule": "incidents awaiting an OSHA recordability determination",
            "unclassified": unclassified, "incidents": int(inc["total"]),
        }
    return "compliant", {
        "rule": "all incidents carry an OSHA recordability determination",
        "incidents": int(inc["total"]),
    }


DERIVATIONS: Dict[str, Derivation] = {
    d.key: d
    for d in (
        Derivation("state_minimum_wage", _derive_minimum_wage, "Minimum wage",
                   required_feature="employees"),
        Derivation("local_minimum_wage", _derive_minimum_wage, "Local minimum wage",
                   required_feature="employees"),
        Derivation("national_minimum_wage", _derive_minimum_wage, "Federal minimum wage",
                   required_feature="employees"),
        Derivation("exempt_salary_threshold", _derive_exempt_salary, "Exempt salary threshold",
                   required_feature="employees"),
        Derivation("harassment_prevention_training", _derive_harassment_training,
                   "Harassment prevention training", required_feature="training"),
        Derivation("injury_illness_recordkeeping", _derive_injury_recordkeeping,
                   "Injury & illness recordkeeping", required_feature="incidents"),
    )
}


def derivable_keys() -> List[str]:
    return sorted(DERIVATIONS)


# ── context (batched once per company — never N+1 per requirement) ──────────

async def _build_context(conn, company_id: UUID, features: Dict[str, Any]) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {"employees": {}, "training": None, "incidents": {}}

    if features.get("employees"):
        for e in await conn.fetch(
            """
            SELECT id, first_name, last_name, pay_classification, pay_rate, work_location_id
            FROM employees
            WHERE org_id = $1 AND termination_date IS NULL AND work_location_id IS NOT NULL
            """,
            company_id,
        ):
            ctx["employees"].setdefault(e["work_location_id"], []).append(dict(e))

    if features.get("training"):
        ctx["training"] = await conn.fetchrow(
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

    if features.get("incidents"):
        for r in await conn.fetch(
            """
            SELECT location_id,
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE osha_recordable IS NULL) AS unclassified
            FROM ir_incidents
            WHERE company_id = $1 AND location_id IS NOT NULL
            GROUP BY location_id
            """,
            company_id,
        ):
            ctx["incidents"][r["location_id"]] = dict(r)

    return ctx


# ── reconcile ───────────────────────────────────────────────────────────────

async def reconcile_requirement_status(
    conn, company_id: UUID, *, features: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Re-derive status for every codified requirement projected to this company.

    Same shape as `compliance_remediation.reconcile_issue_state`: called on the
    read path, idempotent, audit-logs only actual transitions. Only rows linked
    to a catalog entry participate — an unlinked projection row has no stable
    identity to hang status on and fails the codified gate anyway.
    """
    if features is None:
        from ..feature_flags import get_company_features  # local: avoids a cycle
        features = await get_company_features(company_id)

    rows = await conn.fetch(
        """
        SELECT cr.location_id, cat.id AS catalog_id, cat.regulation_key,
               cat.numeric_value, cat.category, cat.rate_type
        FROM compliance_requirements cr
        JOIN business_locations bl ON bl.id = cr.location_id
        JOIN jurisdiction_requirements cat ON cat.id = cr.jurisdiction_requirement_id
        WHERE bl.company_id = $1 AND COALESCE(bl.is_active, true) = true
          AND cat.regulation_key = ANY($2::text[])
        """,
        company_id, derivable_keys(),
    )
    if not rows:
        return {"evaluated": 0, "changed": 0}

    ctx = await _build_context(conn, company_id, features)

    existing = {
        (r["location_id"], r["jurisdiction_requirement_id"]): dict(r)
        for r in await conn.fetch(
            """
            SELECT location_id, jurisdiction_requirement_id, status, basis,
                   attested_note, attested_at
            FROM requirement_compliance_status WHERE company_id = $1
            """,
            company_id,
        )
    }

    evaluated = changed = 0
    for row in rows:
        d = DERIVATIONS.get(row["regulation_key"])
        if d is None:
            continue
        # A feature we cannot see through is a blind spot, not a violation.
        derived: DerivationResult = None
        if d.required_feature is None or features.get(d.required_feature):
            try:
                derived = await d.fn(
                    conn, company_id=company_id, location_id=row["location_id"],
                    row=dict(row), ctx=ctx,
                )
            except Exception:  # noqa: BLE001 — one bad rule must not sink the read
                logger.exception("derivation %s failed", d.key)
                derived = None

        prev = existing.get((row["location_id"], row["catalog_id"]))
        attested = None
        if prev and prev.get("basis") == "attested":
            attested = {
                "status": prev["status"], "note": prev.get("attested_note"),
                "at": prev["attested_at"].isoformat() if prev.get("attested_at") else None,
            }

        status, basis, evidence = resolve_status(derived, attested)
        evaluated += 1
        if prev and prev["status"] == status and prev.get("basis") == basis:
            continue

        await conn.execute(
            """
            INSERT INTO requirement_compliance_status
                (company_id, location_id, jurisdiction_requirement_id, regulation_key,
                 status, basis, evidence, derived_at, updated_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,
                    CASE WHEN $6 = 'derived' THEN NOW() END, NOW())
            ON CONFLICT (location_id, jurisdiction_requirement_id) DO UPDATE SET
                status = EXCLUDED.status,
                basis = EXCLUDED.basis,
                evidence = EXCLUDED.evidence,
                derived_at = COALESCE(EXCLUDED.derived_at,
                                      requirement_compliance_status.derived_at),
                updated_at = NOW()
            """,
            company_id, row["location_id"], row["catalog_id"], row["regulation_key"],
            status, basis, json.dumps(evidence),
        )
        await conn.execute(
            """
            INSERT INTO requirement_status_audit_log
                (company_id, location_id, jurisdiction_requirement_id, action,
                 from_status, to_status, basis, details)
            VALUES ($1,$2,$3,'derived',$4,$5,$6,$7::jsonb)
            """,
            company_id, row["location_id"], row["catalog_id"],
            (prev or {}).get("status"), status, basis, json.dumps(evidence),
        )
        changed += 1

    return {"evaluated": evaluated, "changed": changed}


async def attest_requirement_status(
    conn, *, company_id: UUID, location_id: UUID, catalog_id: UUID,
    status: str, note: Optional[str], actor_user_id: UUID,
) -> Dict[str, Any]:
    """Record a human's declaration for a requirement the system cannot judge.

    Refused where a derivation owns the key: letting an attestation overwrite a
    deterministic fact would let a tenant assert away a violation their own
    payroll data proves. `resolve_status` would drop it on the next reconcile
    anyway — refusing here makes the "no" legible instead of mysterious.
    """
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}")

    key = await conn.fetchval(
        "SELECT regulation_key FROM jurisdiction_requirements WHERE id = $1", catalog_id
    )
    if key in DERIVATIONS:
        raise PermissionError(
            f"{key!r} is derived from your own records and cannot be attested"
        )

    prev = await conn.fetchval(
        """
        SELECT status FROM requirement_compliance_status
        WHERE location_id = $1 AND jurisdiction_requirement_id = $2
        """,
        location_id, catalog_id,
    )
    await conn.execute(
        """
        INSERT INTO requirement_compliance_status
            (company_id, location_id, jurisdiction_requirement_id, regulation_key,
             status, basis, evidence, attested_by, attested_at, attested_note, updated_at)
        VALUES ($1,$2,$3,$4,$5,'attested',$6::jsonb,$7,NOW(),$8,NOW())
        ON CONFLICT (location_id, jurisdiction_requirement_id) DO UPDATE SET
            status = EXCLUDED.status, basis = 'attested',
            evidence = EXCLUDED.evidence, attested_by = EXCLUDED.attested_by,
            attested_at = NOW(), attested_note = EXCLUDED.attested_note, updated_at = NOW()
        """,
        company_id, location_id, catalog_id, key, status,
        json.dumps({"note": note}), actor_user_id, note,
    )
    await conn.execute(
        """
        INSERT INTO requirement_status_audit_log
            (company_id, location_id, jurisdiction_requirement_id, action,
             from_status, to_status, basis, actor_user_id, details)
        VALUES ($1,$2,$3,'attested',$4,$5,'attested',$6,$7::jsonb)
        """,
        company_id, location_id, catalog_id, prev, status, actor_user_id,
        json.dumps({"note": note}),
    )
    return {"status": status, "basis": "attested"}
