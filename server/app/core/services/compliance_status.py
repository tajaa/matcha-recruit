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
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import UUID

from app.matcha.services.scheduling.schedule_rules import INACTIVE_EMPLOYMENT_STATUSES

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

    ``context_group`` names the `_build_context` group this derivation reads —
    used to narrow which groups get built for a given candidate-row set (a
    checklist read for one requirement has no business scanning the whole
    company's roster for a derivation it never calls). ``source_label`` is the
    human-readable source shown in the audit-reveal UI ("Screening
    training_records") — kept server-side so the client never has to
    re-implement this registry.
    """
    key: str
    fn: Callable[..., Awaitable[DerivationResult]]
    label: str
    required_feature: Optional[str] = None
    context_group: Optional[str] = None
    source_label: Optional[str] = None


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


# ── SB 553 component derivations ────────────────────────────────────────────
# One of the five WVP obligations is provable from data already held; the
# other four (written plan, violent incident log, hazard assessment, annual
# review) have no system record and stay attest-only — see
# COMPONENT_DERIVATIONS below.
#
# The violent-incident-log obligation (§6401.9(c)) used to be "derived" from a
# free-text ILIKE match against ir_incidents — but a matching incident title
# proves an incident was mentioned, not that the STATUTE's log (with its
# required fields and 5-year retention) exists. That is exactly the overclaim
# this module's invariants exist to block, so it stays attest-only until a
# structured WVP-log field exists to derive it from.

_ANNUAL_TRAINING_WINDOW_DAYS = 396  # 12 months + slack


async def _derive_wvp_training(
    conn, *, company_id: UUID, location_id: UUID, row: Dict[str, Any], ctx: Dict[str, Any]
) -> DerivationResult:
    """Annual workplace-violence-prevention training, from training_records.

    Same blind/in-progress/compliant shape as `_derive_harassment_training`,
    plus a lapse check: SB 553 training is annual, so "88 assigned, 88
    completed" is not "compliant" if 87 of those people last trained 18 months
    ago. Every count here is PER ACTIVE EMPLOYEE (see the ctx query) — one
    person's three yearly completions are one current employee, not two lapses
    — keyed on each employee's most recent completion: inside the 12-month
    window (`current_completed`), undated with nothing dated proving otherwise
    (`completed_undated` — a dated completion inside the window still wins
    over a stray undated record), or stale (`lapsed`).
    """
    tr = ctx.get("wvp_training")
    if tr is None or int(tr["assigned"] or 0) == 0:
        return None  # Nothing assigned: cannot tell trained-and-unrecorded from
        # untrained. Blind, not violating.
    assigned = int(tr["assigned"])
    completed = int(tr["completed"] or 0)
    if completed < assigned:
        return "in_progress", {
            "rule": "annual WVP training assigned but incomplete",
            "completed": completed, "assigned": assigned,
        }

    current = int(tr["current_completed"] or 0)
    undated = int(tr["completed_undated"] or 0)
    # Every employee who has completed is exactly one of: last completion
    # inside the 12mo window (current), blind-undated (no dated completion
    # proves either currency or lapse), or outside the window (lapsed) — the
    # ctx query's completed_undated already excludes anyone current counted.
    lapsed = completed - current - undated
    last = tr["last_completed"]
    oldest = tr["oldest_completed"]

    if lapsed > 0:
        return "non_compliant", {
            "rule": "annual WVP training lapsed for one or more employees "
                    "(over 12 months since their last completion)",
            "lapsed": lapsed, "completed": completed, "assigned": assigned,
            "oldest_completed": oldest.isoformat() if oldest else None,
        }
    if undated > 0:
        # Completed but with no date on file: cannot prove it falls inside the
        # 12-month window, so it cannot count as currently compliant — but it
        # is also not proof of a lapse. Blind on currency, not violating.
        return "in_progress", {
            "rule": "annual WVP training completed but undated — cannot confirm currency",
            "undated": undated, "completed": completed, "assigned": assigned,
        }
    return "compliant", {
        "rule": "annual WVP training complete and current",
        "completed": completed, "assigned": assigned,
        "last_completed": last.isoformat() if last else None,
    }


COMPONENT_DERIVATIONS: Dict[str, Derivation] = {
    "wvp_training": Derivation(
        "wvp_training", _derive_wvp_training, "SB 553 annual training",
        required_feature="training", context_group="wvp_training",
        source_label="training_records"),
}


def component_derivation(derivation_key: Optional[str]) -> Optional[Derivation]:
    if derivation_key is None:
        return None
    return COMPONENT_DERIVATIONS.get(derivation_key)


def derivable_component_keys() -> List[str]:
    return sorted(COMPONENT_DERIVATIONS)


# ── workforce-compliance verdicts (pure, one source of truth) ───────────────
# Used BOTH by the DERIVATIONS below (per catalog requirement, where 'unknown'
# means "blind → return None") and by the workforce-page requirement gate
# (matcha/services/workforce_requirement_gate.py, where 'unknown' is shown as
# "not yet tracked"). Same rule, two presentations — never two copies of it.

def pay_transparency_verdict(status_str: Optional[str]) -> Tuple[str, str]:
    if status_str == "compliant":
        return "compliant", "job postings include salary ranges"
    if status_str == "action_needed":
        return "non_compliant", "state requires salary ranges in postings; not yet confirmed"
    return "unknown", "this state not yet marked on the pay-transparency tracker"


def pay_equity_verdict(review: Optional[Dict[str, Any]]) -> Tuple[str, str]:
    if not review:
        return "unknown", "no pay-equity study on file"
    if review.get("overdue"):
        return "in_progress", "pay-equity study overdue for refresh"
    gap = review.get("gap_pct")
    if gap is not None and float(gap) > 5 and not (review.get("remediation") or "").strip():
        return "non_compliant", f"pay-equity study shows a {float(gap):.1f}% unremediated gap"
    if gap is None:
        # A dispersion-only study satisfies the "have a current study" obligation, but
        # says nothing about a protected-class gap — the thing the statute is about.
        # Named here so this doesn't read as a clean bill of health, and so it doesn't
        # contradict workforce_compliance.derive_pay_equity, which scores loud spread
        # down on the same row.
        return "compliant", "current pay-equity study on file (dispersion screen only — no measured gap)"
    return "compliant", "current pay-equity study on file"


def biometrics_verdict(registered: int, missing: int) -> Tuple[str, str]:
    if registered == 0:
        return "unknown", "no biometric collection points registered"
    if missing:
        return "non_compliant", f"{missing} biometric collection point(s) without consent on file"
    return "compliant", "all biometric collection points have consent"


def _verdict_to_derivation(status: str, reason: str, **extra: Any) -> DerivationResult:
    """A verdict → a DerivationResult, turning 'unknown' into None (blind, per the
    module's rule that we never certify or invent what we cannot see)."""
    if status == "unknown":
        return None
    return status, {"rule": reason, **extra}


async def _derive_pay_transparency(
    conn, *, company_id: UUID, location_id: UUID, row: Dict[str, Any], ctx: Dict[str, Any]
) -> DerivationResult:
    """Per-state salary-range posting law, keyed on THIS location's state — a company
    compliant in CA but not CO is non-compliant only at the CO location."""
    state = (ctx.get("locations") or {}).get(location_id)
    if not state:
        return None
    row_pt = (ctx.get("pay_transparency") or {}).get(state.upper())
    status, reason = pay_transparency_verdict(row_pt.get("status") if row_pt else None)
    return _verdict_to_derivation(status, reason, state=state)


async def _derive_pay_equity(
    conn, *, company_id: UUID, location_id: UUID, row: Dict[str, Any], ctx: Dict[str, Any]
) -> DerivationResult:
    status, reason = pay_equity_verdict(ctx.get("pay_equity"))
    return _verdict_to_derivation(status, reason)


async def _derive_biometrics(
    conn, *, company_id: UUID, location_id: UUID, row: Dict[str, Any], ctx: Dict[str, Any]
) -> DerivationResult:
    bio = ctx.get("biometrics") or {}
    status, reason = biometrics_verdict(int(bio.get("registered") or 0), int(bio.get("missing_consent") or 0))
    return _verdict_to_derivation(status, reason)


DERIVATIONS: Dict[str, Derivation] = {
    d.key: d
    for d in (
        Derivation("state_minimum_wage", _derive_minimum_wage, "Minimum wage",
                   required_feature="employees", context_group="employees"),
        Derivation("local_minimum_wage", _derive_minimum_wage, "Local minimum wage",
                   required_feature="employees", context_group="employees"),
        Derivation("national_minimum_wage", _derive_minimum_wage, "Federal minimum wage",
                   required_feature="employees", context_group="employees"),
        Derivation("exempt_salary_threshold", _derive_exempt_salary, "Exempt salary threshold",
                   required_feature="employees", context_group="employees"),
        Derivation("harassment_prevention_training", _derive_harassment_training,
                   "Harassment prevention training", required_feature="training",
                   context_group="training"),
        Derivation("injury_illness_recordkeeping", _derive_injury_recordkeeping,
                   "Injury & illness recordkeeping", required_feature="incidents",
                   context_group="incidents"),
        # Workforce-compliance trackers as the backstop for their matching
        # jurisdiction requirements. Same data epl_readiness derives its EPL
        # factors from — the workforce page is where the business maintains it.
        # (AI hiring-tool / LL144 has no catalog regulation_key yet, so there is
        # nothing to derive against — it stays self-tracked on the page.)
        Derivation("pay_transparency", _derive_pay_transparency, "Pay transparency",
                   required_feature="workforce_compliance", context_group="workforce"),
        Derivation("federal_equal_pay", _derive_pay_equity, "Pay equity",
                   required_feature="workforce_compliance", context_group="workforce"),
        Derivation("pay_equity", _derive_pay_equity, "Pay equity",
                   required_feature="workforce_compliance", context_group="workforce"),
        Derivation("state_biometric_privacy_laws", _derive_biometrics, "Biometric privacy",
                   required_feature="workforce_compliance", context_group="workforce"),
    )
}


def derivable_keys() -> List[str]:
    return sorted(DERIVATIONS)


# ── context group narrowing ─────────────────────────────────────────────────
# Every group `_build_context` knows how to build. A candidate-row set for one
# requirement (or one component) only ever needs the groups its OWN
# derivations read — building all of them on every reconcile is how a
# checklist GET ends up scanning the whole company's roster for a derivation
# it never calls.
CTX_GROUPS = ("employees", "training", "incidents", "wvp_training", "workforce")


def _context_groups_for(
    registry: Dict[str, Derivation], keys: Iterable[Optional[str]]
) -> set:
    """The context_group values the given registry keys' derivations read.

    Unknown/None keys are ignored (a row with no matching derivation reads no
    context) rather than erroring — the caller has already filtered candidate
    rows to what it will actually evaluate, but staying permissive here means
    a caller that hasn't is just a no-op for the row it can't derive anyway.
    """
    groups = set()
    for key in keys:
        d = registry.get(key) if key is not None else None
        if d is not None and d.context_group is not None:
            groups.add(d.context_group)
    return groups


# ── context (batched once per company — never N+1 per requirement) ──────────

async def _build_context(
    conn, company_id: UUID, features: Dict[str, Any], *,
    groups: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Batch-load the evidence every derivation reads, narrowed to `groups`.

    `groups=None` (the default) builds everything — used by any caller that
    hasn't narrowed its candidate rows yet. Every group key is always present
    in the returned dict (empty/None, per group) even when not built, so a
    derivation reading an un-built group sees exactly what it sees for an
    unsold feature: nothing there, blind, never a violation.
    """
    build = CTX_GROUPS if groups is None else set(groups)
    ctx: Dict[str, Any] = {
        "employees": {}, "training": None, "incidents": {}, "wvp_training": None,
        # workforce group — seeded here so the docstring's promise holds for it
        # too. A derivation written as ctx["locations"] (the direct-index style
        # the older derivations use) would otherwise KeyError on an unbuilt
        # group, and reconcile swallows that into a silent `unknown`.
        "locations": {}, "pay_transparency": {}, "pay_equity": None, "biometrics": {},
    }

    if "employees" in build and features.get("employees"):
        for e in await conn.fetch(
            """
            SELECT id, first_name, last_name, pay_classification, pay_rate, work_location_id
            FROM employees
            WHERE org_id = $1 AND termination_date IS NULL AND work_location_id IS NOT NULL
              AND COALESCE(employment_status, 'active') <> ALL($2::text[])
            """,
            company_id,
            list(INACTIVE_EMPLOYMENT_STATUSES),
        ):
            ctx["employees"].setdefault(e["work_location_id"], []).append(dict(e))

    if "training" in build and features.get("training"):
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

    if "incidents" in build and features.get("incidents"):
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

    # SB 553-shaped context. Deliberately separate from ctx["training"] (which
    # is filtered to harassment/EEO training and says nothing about workplace
    # violence) — reusing it would silently grade the wrong thing.
    if "wvp_training" in build and features.get("training"):
        # Counted PER EMPLOYEE, not per record. training_records accumulates one
        # row per employee per annual cycle (the active-assignment unique index
        # only covers status IN ('assigned','in_progress'), so completions pile
        # up), and terminated employees' history never goes away. Counting rows
        # scores last year's on-time completion as this year's lapse — a company
        # that trains exactly on schedule would be reported non_compliant, which
        # is precisely the manufactured violation this module must never emit.
        # Waived rows are dropped (no obligation) and terminated/offboarded
        # employees with them, so a departed worker can't pin the verdict at
        # in_progress or non_compliant. termination_date IS NULL alone is not
        # enough — the status-change endpoint (employees/crud.py PUT .../status)
        # writes employment_status without ever touching termination_date, so
        # the two columns drift; a NULL employment_status still means active
        # (nullable column, DEFAULT 'active').
        ctx["wvp_training"] = await conn.fetchrow(
            """
            WITH per_employee AS (
                SELECT tr.employee_id,
                       BOOL_OR(tr.status = 'completed') AS ever_completed,
                       BOOL_OR(tr.status = 'completed' AND tr.completed_date IS NULL)
                         AS has_undated,
                       MAX(tr.completed_date) FILTER (WHERE tr.status = 'completed')
                         AS last_completed
                FROM training_records tr
                JOIN employees e ON e.id = tr.employee_id
                WHERE tr.company_id = $1
                  AND tr.status <> 'waived'
                  AND e.termination_date IS NULL
                  AND COALESCE(e.employment_status, 'active') <> ALL($3::text[])
                  AND (tr.training_type = 'workplace_violence'
                       OR LOWER(tr.title) ~ '(workplace violence|wvp|sb ?553)')
                GROUP BY tr.employee_id
            )
            SELECT COUNT(*) AS assigned,
                   COUNT(*) FILTER (WHERE ever_completed) AS completed,
                   COUNT(*) FILTER (WHERE last_completed >= $2) AS current_completed,
                   -- Undated (blind), not lapsed: an employee with an undated
                   -- completion and no dated completion inside the window —
                   -- either because they have no dated completion at all, or
                   -- their only dated one is stale — cannot be proven current
                   -- OR proven lapsed. A dated completion already inside the
                   -- window (caught by current_completed above) still wins:
                   -- an extra undated record can't demote a provably-current
                   -- employee.
                   COUNT(*) FILTER (
                       WHERE ever_completed AND has_undated
                         AND (last_completed IS NULL OR last_completed < $2)
                   ) AS completed_undated,
                   MIN(last_completed) AS oldest_completed,
                   MAX(last_completed) AS last_completed
            FROM per_employee
            """,
            company_id,
            date.today() - timedelta(days=_ANNUAL_TRAINING_WINDOW_DAYS),
            list(INACTIVE_EMPLOYMENT_STATUSES),
        )

    # Workforce-compliance backstops (pay transparency / pay equity / biometrics).
    # Loaded once here so the per-requirement derivations never re-query.
    if "workforce" in build and features.get("workforce_compliance"):
        ctx["locations"] = {
            r["id"]: r["state"]
            for r in await conn.fetch(
                # Active only — a deactivated location must not go on driving a
                # per-location pay-transparency verdict. Mirrors the same filter in
                # matcha/services/workforce_requirement_gate.
                "SELECT id, state FROM business_locations "
                "WHERE company_id = $1 AND COALESCE(is_active, true) = true", company_id,
            )
        }
        ctx["pay_transparency"] = {
            r["state"].upper(): dict(r)
            for r in await conn.fetch(
                "SELECT state, status FROM pay_transparency_status WHERE company_id = $1", company_id,
            )
            if r["state"]
        }
        ctx["pay_equity"] = await conn.fetchrow(
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
        ctx["biometrics"] = dict(bio) if bio else {}

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
        # conn=, always: the caller already holds one, and acquiring a second
        # under it deadlocks the pool at concurrency == pool_size.
        features = await get_company_features(company_id, conn=conn)

    # The codified gate, same as every tenant-facing read. Without it a status —
    # and the issue it raises — could attach to a catalog row the tenant cannot
    # see anywhere in their requirements tab: told they are non-compliant with a
    # law the product refuses to show them.
    from .compliance_service import codified_gate_sql

    rows = await conn.fetch(
        f"""
        SELECT DISTINCT cr.location_id, cat.id AS catalog_id, cat.regulation_key,
               cat.numeric_value, cat.category, cat.rate_type
        FROM compliance_requirements cr
        JOIN business_locations bl ON bl.id = cr.location_id
        JOIN jurisdiction_requirements cat ON cat.id = cr.jurisdiction_requirement_id
        WHERE bl.company_id = $1 AND COALESCE(bl.is_active, true) = true
          AND cat.regulation_key = ANY($2::text[])
          {await codified_gate_sql("cat", conn=conn)}
        """,
        company_id, derivable_keys(),
    )
    if not rows:
        return {"evaluated": 0, "changed": 0}

    ctx = await _build_context(
        conn, company_id, features,
        groups=_context_groups_for(DERIVATIONS, (r["regulation_key"] for r in rows)),
    )

    existing = {
        (r["location_id"], r["jurisdiction_requirement_id"]): dict(r)
        for r in await conn.fetch(
            """
            SELECT location_id, jurisdiction_requirement_id, status, basis,
                   attested_note, attested_at
            FROM requirement_compliance_status
            WHERE company_id = $1 AND component_key IS NULL
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
            VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,NOW())
            ON CONFLICT (location_id, jurisdiction_requirement_id, COALESCE(component_key, ''))
                DO UPDATE SET
                status = EXCLUDED.status,
                basis = EXCLUDED.basis,
                evidence = EXCLUDED.evidence,
                -- Keep the first derivation's timestamp when this pass was an
                -- attestation: derived_at means "when we last checked the data",
                -- and an attestation checked nothing.
                derived_at = COALESCE(EXCLUDED.derived_at,
                                      requirement_compliance_status.derived_at),
                updated_at = NOW()
            """,
            company_id, row["location_id"], row["catalog_id"], row["regulation_key"],
            status, basis, json.dumps(evidence),
            # Decided here rather than with a CASE on $6: that placeholder also
            # feeds the `basis` varchar column, and asyncpg's prepare then fails
            # with "inconsistent types deduced for parameter $6".
            datetime.now(timezone.utc) if basis == "derived" else None,
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
          AND component_key IS NULL
        """,
        location_id, catalog_id,
    )
    await conn.execute(
        """
        INSERT INTO requirement_compliance_status
            (company_id, location_id, jurisdiction_requirement_id, regulation_key,
             status, basis, evidence, attested_by, attested_at, attested_note, updated_at)
        VALUES ($1,$2,$3,$4,$5,'attested',$6::jsonb,$7,NOW(),$8,NOW())
        ON CONFLICT (location_id, jurisdiction_requirement_id, COALESCE(component_key, ''))
            DO UPDATE SET
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


# ── component checklist ──────────────────────────────────────────────────────

async def fetch_requirement_components(
    conn, catalog_ids: Sequence[UUID]
) -> Dict[UUID, List[Dict[str, Any]]]:
    """Catalog-side decomposition for a batch of requirements. Never N+1 per
    requirement — callers pass every catalog id they need up front."""
    if not catalog_ids:
        return {}
    rows = await conn.fetch(
        """
        SELECT id, jurisdiction_requirement_id, component_key, label, question,
               statute_citation, suggested_fix, severity, derivation_key, sort_order
        FROM requirement_components
        WHERE jurisdiction_requirement_id = ANY($1::uuid[])
        ORDER BY jurisdiction_requirement_id, sort_order
        """,
        list(catalog_ids),
    )
    out: Dict[UUID, List[Dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r["jurisdiction_requirement_id"], []).append(dict(r))
    return out


async def reconcile_component_status(
    conn, company_id: UUID, *, features: Optional[Dict[str, Any]] = None,
    location_id: Optional[UUID] = None, catalog_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    """Re-derive status for every component of every codified requirement that
    HAS components, projected to this company.

    Mirrors `reconcile_requirement_status` (idempotent, read-path safe,
    audit-logs only real transitions) with three differences: the identity key
    is the 3-tuple (location, catalog, component) instead of 2; the candidate
    row set comes from a join against `requirement_components` rather than a
    filter on `derivable_keys()` — an attest-only component has no
    `DERIVATIONS` entry and would otherwise never get evaluated; and both
    `location_id`/`catalog_id` are optional narrowing filters so a single
    checklist read (`get_component_checklist`) can reconcile just its own row
    instead of the whole company.
    """
    if features is None:
        from ..feature_flags import get_company_features  # local: avoids a cycle
        # conn=, always: the caller already holds one, and acquiring a second
        # under it deadlocks the pool at concurrency == pool_size.
        features = await get_company_features(company_id, conn=conn)

    from .compliance_service import codified_gate_sql

    params: List[Any] = [company_id]
    filters = ["bl.company_id = $1", "COALESCE(bl.is_active, true) = true"]
    if location_id is not None:
        params.append(location_id)
        filters.append(f"cr.location_id = ${len(params)}")
    if catalog_id is not None:
        params.append(catalog_id)
        filters.append(f"cat.id = ${len(params)}")

    rows = await conn.fetch(
        f"""
        SELECT DISTINCT cr.location_id, cat.id AS catalog_id, rc.component_key,
               rc.derivation_key
        FROM compliance_requirements cr
        JOIN business_locations bl ON bl.id = cr.location_id
        JOIN jurisdiction_requirements cat ON cat.id = cr.jurisdiction_requirement_id
        JOIN requirement_components rc ON rc.jurisdiction_requirement_id = cat.id
        WHERE {' AND '.join(filters)}
          {await codified_gate_sql("cat", conn=conn)}
        """,
        *params,
    )
    if not rows:
        return {"evaluated": 0, "changed": 0}

    ctx = await _build_context(
        conn, company_id, features,
        groups=_context_groups_for(COMPONENT_DERIVATIONS, (r["derivation_key"] for r in rows)),
    )

    existing = {
        (r["location_id"], r["jurisdiction_requirement_id"], r["component_key"]): dict(r)
        for r in await conn.fetch(
            """
            SELECT location_id, jurisdiction_requirement_id, component_key,
                   status, basis, attested_note, attested_at
            FROM requirement_compliance_status
            WHERE company_id = $1 AND component_key IS NOT NULL
            """,
            company_id,
        )
    }

    evaluated = changed = 0
    for row in rows:
        d = component_derivation(row["derivation_key"])
        derived: DerivationResult = None
        if d is not None and (d.required_feature is None or features.get(d.required_feature)):
            try:
                derived = await d.fn(
                    conn, company_id=company_id, location_id=row["location_id"],
                    row=dict(row), ctx=ctx,
                )
            except Exception:  # noqa: BLE001 — one bad rule must not sink the read
                logger.exception("component derivation %s failed", d.key)
                derived = None

        key3 = (row["location_id"], row["catalog_id"], row["component_key"])
        prev = existing.get(key3)
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
                (company_id, location_id, jurisdiction_requirement_id, component_key,
                 regulation_key, status, basis, evidence, derived_at, updated_at)
            VALUES ($1,$2,$3,$4,NULL,$5,$6,$7::jsonb,$8,NOW())
            ON CONFLICT (location_id, jurisdiction_requirement_id, COALESCE(component_key, ''))
                DO UPDATE SET
                status = EXCLUDED.status,
                basis = EXCLUDED.basis,
                evidence = EXCLUDED.evidence,
                derived_at = COALESCE(EXCLUDED.derived_at,
                                      requirement_compliance_status.derived_at),
                updated_at = NOW()
            """,
            company_id, row["location_id"], row["catalog_id"], row["component_key"],
            status, basis, json.dumps(evidence),
            datetime.now(timezone.utc) if basis == "derived" else None,
        )
        await conn.execute(
            """
            INSERT INTO requirement_status_audit_log
                (company_id, location_id, jurisdiction_requirement_id, component_key,
                 action, from_status, to_status, basis, details)
            VALUES ($1,$2,$3,$4,'derived',$5,$6,$7,$8::jsonb)
            """,
            company_id, row["location_id"], row["catalog_id"], row["component_key"],
            (prev or {}).get("status"), status, basis, json.dumps(evidence),
        )
        changed += 1

    return {"evaluated": evaluated, "changed": changed}


async def get_component_checklist(
    conn, *, company_id: UUID, location_id: UUID, catalog_id: UUID,
) -> Dict[str, Any]:
    """One requirement's components + per-component status + rollup, scoped to
    a single (company, location, catalog) triple. Reconciles just that scope
    first (cheap — a handful of rows, not the whole company) then reads back."""
    await reconcile_component_status(
        conn, company_id, location_id=location_id, catalog_id=catalog_id,
    )

    components = (await fetch_requirement_components(conn, [catalog_id])).get(catalog_id, [])
    statuses = {
        r["component_key"]: dict(r)
        for r in await conn.fetch(
            """
            SELECT component_key, status, basis, evidence, attested_note, attested_at, derived_at
            FROM requirement_compliance_status
            WHERE company_id = $1 AND location_id = $2 AND jurisdiction_requirement_id = $3
              AND component_key IS NOT NULL
            """,
            company_id, location_id, catalog_id,
        )
    }

    out_components: List[Dict[str, Any]] = []
    status_rows: List[Dict[str, Any]] = []
    for c in components:
        st = statuses.get(c["component_key"], {})
        # Registry-resolved, not a bare `derivation_key is not None` — a
        # catalog row can carry a stale/dropped derivation_key (exactly what
        # happened when wvp_incident_log was retired) and this must agree
        # with attest_component_status's own refusal check below, or the FE
        # hides the attest button for a clause the server will happily
        # accept an attestation on.
        d = component_derivation(c["derivation_key"])
        merged = {
            **c,
            "derivable": d is not None,
            "derivation_source": d.source_label if d is not None else None,
            "status": st.get("status", "unknown"),
            "basis": st.get("basis"),
            "evidence": (json.loads(st["evidence"]) if isinstance(st.get("evidence"), str)
                         else (st.get("evidence") or {})),
            "attested_note": st.get("attested_note"),
            "attested_at": st["attested_at"].isoformat() if st.get("attested_at") else None,
            "derived_at": st["derived_at"].isoformat() if st.get("derived_at") else None,
        }
        out_components.append(merged)
        status_rows.append({"status": merged["status"], "basis": merged["basis"]})

    return {"components": out_components, "summary": rollup(status_rows)}


async def attest_component_status(
    conn, *, company_id: UUID, location_id: UUID, catalog_id: UUID,
    component_key: str, status: str, note: Optional[str], actor_user_id: UUID,
) -> Dict[str, Any]:
    """Human declaration for ONE component of a decomposed requirement.

    Refused only when THIS component carries a `derivation_key` — unlike
    `attest_requirement_status`'s whole-key refusal, a sibling component with
    no derivation must stay attestable even after another component on the
    same requirement becomes derivable. Getting this wrong (checking the
    parent regulation_key instead of the component) would block attestation on
    every non-derivable clause of a statute the moment ONE clause of it gains a
    derivation.
    """
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}")

    comp = await conn.fetchrow(
        "SELECT derivation_key FROM requirement_components "
        "WHERE jurisdiction_requirement_id = $1 AND component_key = $2",
        catalog_id, component_key,
    )
    if comp is None:
        raise ValueError(f"no such component {component_key!r} on this requirement")
    if comp["derivation_key"] and component_derivation(comp["derivation_key"]) is not None:
        raise PermissionError(
            f"{component_key!r} is derived from your own records and cannot be attested"
        )

    prev = await conn.fetchval(
        """
        SELECT status FROM requirement_compliance_status
        WHERE location_id = $1 AND jurisdiction_requirement_id = $2 AND component_key = $3
        """,
        location_id, catalog_id, component_key,
    )
    await conn.execute(
        """
        INSERT INTO requirement_compliance_status
            (company_id, location_id, jurisdiction_requirement_id, component_key,
             regulation_key, status, basis, evidence, attested_by, attested_at,
             attested_note, updated_at)
        VALUES ($1,$2,$3,$4,NULL,$5,'attested',$6::jsonb,$7,NOW(),$8,NOW())
        ON CONFLICT (location_id, jurisdiction_requirement_id, COALESCE(component_key, ''))
            DO UPDATE SET
            status = EXCLUDED.status, basis = 'attested',
            evidence = EXCLUDED.evidence, attested_by = EXCLUDED.attested_by,
            attested_at = NOW(), attested_note = EXCLUDED.attested_note, updated_at = NOW()
        """,
        company_id, location_id, catalog_id, component_key, status,
        json.dumps({"note": note}), actor_user_id, note,
    )
    await conn.execute(
        """
        INSERT INTO requirement_status_audit_log
            (company_id, location_id, jurisdiction_requirement_id, component_key,
             action, from_status, to_status, basis, actor_user_id, details)
        VALUES ($1,$2,$3,$4,'attested',$5,$6,'attested',$7,$8::jsonb)
        """,
        company_id, location_id, catalog_id, component_key, prev, status, actor_user_id,
        json.dumps({"note": note}),
    )
    return {"status": status, "basis": "attested"}


# ── company-wide audit overview ──────────────────────────────────────────────

async def get_company_audit_overview(
    conn, company_id: UUID, *, features: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Every decomposed requirement projected to this company, grouped by
    statute then location — the Audit tab's one aggregate read.

    Four steps, in this order because the order is what keeps it both correct
    and cheap:

    1. Short-circuit on whether ANY component row is even projected. Empty for
       every tenant except one with a decomposed statute in its jurisdictions
       (today: CA only) — that tenant pays one query and zero pipeline runs.
    2. One company-wide reconcile (never per-location — `_context_groups_for`
       already narrows `_build_context` to the single aggregate the surviving
       derivation reads).
    3. One grouped status read, joined to `requirement_components` so orphaned
       component rows cannot count, and ordered so the rendering is stable.
    4. A visibility pass, ONLY for the locations named by BOTH steps above.
       This cannot be collapsed into a single query: `_filter_with_preemption`
       / `_filter_city_level_requirements` are set-relative — they decide by
       comparing sibling requirement rows in the same category group — so a
       query narrowed to one catalog row cannot reproduce the answer. Same
       invariant `_assert_component_requirement_visible` enforces on the
       checklist endpoints: the Audit tab must never show a requirement the
       Requirements tab hides. Step 3's status rows are then assembled and
       dropped against this visible set.
    """
    if features is None:
        from ..feature_flags import get_company_features  # local: avoids a cycle
        # conn=, always: the caller already holds one, and acquiring a second
        # under it deadlocks the pool at concurrency == pool_size.
        features = await get_company_features(company_id, conn=conn)

    from .compliance_service import codified_gate_sql

    # (1) Short-circuit.
    candidate_rows = await conn.fetch(
        f"""
        SELECT DISTINCT cr.location_id, cat.id AS catalog_id
        FROM compliance_requirements cr
        JOIN business_locations bl ON bl.id = cr.location_id
        JOIN jurisdiction_requirements cat ON cat.id = cr.jurisdiction_requirement_id
        JOIN requirement_components rc ON rc.jurisdiction_requirement_id = cat.id
        WHERE bl.company_id = $1 AND COALESCE(bl.is_active, true) = true
          {await codified_gate_sql("cat", conn=conn)}
        """,
        company_id,
    )
    if not candidate_rows:
        return {"statutes": [], "summary": rollup([]), "location_count": 0}

    # (2) One company-wide reconcile.
    await reconcile_component_status(conn, company_id, features=features)

    # (3) Grouped status read.
    #
    # Joined to `requirement_components`, not just filtered on
    # `component_key IS NOT NULL`: there is no FK on that column and nothing
    # deletes stale rows, so a component removed or renamed by a later seed
    # revision leaves status rows behind that would go on counting toward the
    # statute and location rollups — reporting summary.total = 6 against a live
    # component_count of 5, with the orphan's frozen status skewing both.
    #
    # ORDER BY is load-bearing, not cosmetic: the dicts assembled below keep
    # insertion order, so without it two identical requests can render the
    # statute cards — and the location rows inside them — in different orders.
    # An unordered scan guarantees nothing, and the UPDATEs reconcile just ran
    # relocate heap tuples. Sorted on ids as well as labels so ties are stable.
    status_rows = await conn.fetch(
        """
        SELECT rcs.location_id, rcs.jurisdiction_requirement_id AS catalog_id,
               rcs.component_key, rcs.status, rcs.basis,
               cat.title, cat.statute_citation, cat.category,
               j.level::text  AS authority_level,
               j.display_name AS authority_display_name,
               (SELECT count(*) FROM requirement_components rc2
                  WHERE rc2.jurisdiction_requirement_id = cat.id) AS component_count,
               bl.name AS location_name, bl.city, bl.state
        FROM requirement_compliance_status rcs
        JOIN requirement_components rc
          ON rc.jurisdiction_requirement_id = rcs.jurisdiction_requirement_id
         AND rc.component_key = rcs.component_key
        JOIN jurisdiction_requirements cat ON cat.id = rcs.jurisdiction_requirement_id
        JOIN business_locations bl ON bl.id = rcs.location_id
        LEFT JOIN jurisdictions j ON j.id = cat.jurisdiction_id
        WHERE rcs.company_id = $1
          AND rcs.component_key IS NOT NULL
        ORDER BY cat.title, cat.id, bl.name, bl.id, rc.sort_order, rc.component_key
        """,
        company_id,
    )

    # (4) Visibility, only for locations that survived BOTH step 1 and step 3 —
    # a candidate location with no component status row at all contributes
    # nothing downstream, and this pipeline run is the expensive part of the
    # endpoint (a projection query, two set-relative filters and the roster
    # scan in get_employee_impact_for_location, per location).
    # get_location_requirements already filters `l.company_id = $2`, so nothing
    # here can leak a foreign location.
    from .compliance_service import get_location_requirements

    candidate_locations = {r["location_id"] for r in candidate_rows}
    pipeline_locations = sorted(
        candidate_locations & {r["location_id"] for r in status_rows}, key=str
    )
    visible_catalog_ids: Dict[UUID, set] = {}
    employee_counts: Dict[UUID, Optional[int]] = {}
    for loc_id in pipeline_locations:
        reqs = await get_location_requirements(loc_id, company_id, conn=conn)
        visible_catalog_ids[loc_id] = {
            UUID(r.jurisdiction_requirement_id) for r in reqs
            if r.jurisdiction_requirement_id and r.has_components
        }
        # Every row for a location carries the same total_affected — harvest
        # it off whichever row exists rather than a second query.
        employee_counts[loc_id] = reqs[0].affected_employee_count if reqs else None

    from .compliance_service import _authority_label
    from .compliance_risk import loc_label

    # statute_id -> {"header": {...}, "locations": {loc_id: [status_rows]}}
    # loc_meta is captured alongside — every row for a location carries the
    # same bl.name/city/state, so the first row seen for it is as good as any.
    by_statute: Dict[UUID, Dict[str, Any]] = {}
    loc_meta: Dict[UUID, Dict[str, Any]] = {}
    for row in status_rows:
        loc_id, cat_id = row["location_id"], row["catalog_id"]
        if cat_id not in visible_catalog_ids.get(loc_id, set()):
            continue  # hidden by preemption / industry / codified gate at this location
        loc_meta.setdefault(loc_id, {
            "name": row["location_name"], "city": row["city"], "state": row["state"],
        })
        entry = by_statute.setdefault(cat_id, {"header": row, "locations": {}})
        entry["locations"].setdefault(loc_id, []).append(
            {"status": row["status"], "basis": row["basis"]}
        )

    statutes: List[Dict[str, Any]] = []
    all_rows_for_company: List[Dict[str, Any]] = []
    for cat_id, entry in by_statute.items():
        header = entry["header"]
        location_rows = []
        statute_rows: List[Dict[str, Any]] = []
        for loc_id, rows in entry["locations"].items():
            statute_rows.extend(rows)
            location_rows.append({
                "location_id": str(loc_id),
                "location_label": loc_label(loc_meta[loc_id]),
                "employee_count": employee_counts.get(loc_id),
                "summary": rollup(rows),
            })
        statutes.append({
            "jurisdiction_requirement_id": str(cat_id),
            "title": header["title"],
            "statute_citation": header["statute_citation"],
            "category": header["category"],
            "authority_level": header["authority_level"],
            "authority_name": _authority_label(header["authority_level"], header["authority_display_name"]),
            "component_count": header["component_count"],
            "locations": location_rows,
            "summary": rollup(statute_rows),
        })
        all_rows_for_company.extend(statute_rows)

    return {
        "statutes": statutes,
        # The locations actually RENDERED, not the pre-visibility candidate set:
        # a location whose only decomposed statute is preempted or filtered out
        # for this industry has no row in `statutes[].locations`, and counting
        # it here prints "1 statute · 3 locations" above a single location row.
        "location_count": len(loc_meta),
        "summary": rollup(all_rows_for_company),
    }
