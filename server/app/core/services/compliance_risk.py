"""Compliance risk cockpit aggregator.

The manager-facing compliance surface. Its value is not the requirement
catalog but the measured RISK associated with it: what is out of compliance
right now (wage, credentials, incidents, critical alerts), the dollar exposure,
who is affected, and the single deterministic next action for each.

One company-scoped round-trip, no Gemini. Each section is isolated in its own
try/except so a single failing subsystem degrades to fewer issues rather than a
500 — the same posture the dashboard flags builder takes. Recommendation
phrasing mirrors `dashboard._deterministic_flags_from_patterns` without coupling
to the dashboard cache/rebuild machinery.

Reuses:
  - `compliance_service.get_employee_impact_for_location` (per-location wage)
  - the dashboard credential-expiry SQL (inlined; the route keeps its Redis cache)
  - `ir_incidents` open-status convention ('reported','investigating','action_required')
  - penalty context from `jurisdiction_requirements.metadata->'penalties'`
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from uuid import UUID

from ...database import get_connection
from ..feature_flags import get_company_features
from ..models.compliance import (
    ComplianceRiskSummary,
    RiskGetAhead,
    RiskIssue,
    RiskPenalty,
    RiskPosture,
)
from .compliance_service import get_employee_impact_for_location
from .compliance_remediation import fetch_recent_remediations, reconcile_issue_state

logger = logging.getLogger(__name__)

# Open incident statuses — same set the dashboard risk-pattern detector uses.
_OPEN_INCIDENT_STATUSES = ("reported", "investigating", "action_required")

# Credential-type → human label (mirrors dashboard._CREDENTIAL_LABELS).
_CREDENTIAL_LABELS = {
    "medical_license": "Medical License",
    "dea_registration": "DEA Registration",
    "board_certification": "Board Certification",
    "malpractice_insurance": "Malpractice Insurance",
}

_SEV_RANK = {"critical": 0, "high": 1, "moderate": 2}


def _loc_label(row) -> str:
    name = row.get("name")
    city, state = row.get("city"), row.get("state")
    if name:
        return name
    if city and state:
        return f"{city}, {state}"
    return city or state or "Company-wide"


def _parse_penalties(raw) -> dict | None:
    """metadata->'penalties' may arrive as a dict (jsonb) or a JSON string."""
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return None
    return raw if isinstance(raw, dict) else None


async def _wage_penalty_for_location(conn, jurisdiction_id, rate_type: str) -> tuple[RiskPenalty | None, str | None]:
    """Resolve the minimum-wage catalog row governing this location + rate type
    and return its statutory penalty context + citation. Walks the jurisdiction
    chain city→…→federal and takes the nearest row that names the requirement;
    penalties (and citation) ride whichever chain row carries them."""
    if jurisdiction_id is None:
        return None, None
    row = await conn.fetchrow(
        """
        WITH RECURSIVE chain AS (
            SELECT id, parent_id, level, 0 AS depth
            FROM jurisdictions WHERE id = $1
            UNION ALL
            SELECT j.id, j.parent_id, j.level, c.depth + 1
            FROM jurisdictions j JOIN chain c ON j.id = c.parent_id
            WHERE c.depth < 10  -- cycle guard: chain is federal→…→city, never deep
        )
        SELECT jr.statute_citation, jr.metadata->'penalties' AS penalties
        FROM chain c
        JOIN jurisdiction_requirements jr ON jr.jurisdiction_id = c.id
        WHERE jr.category = 'minimum_wage'
          AND COALESCE(jr.rate_type, 'general') = $2
          AND jr.status = 'active'
        ORDER BY (jr.metadata ? 'penalties') DESC, c.depth ASC
        LIMIT 1
        """,
        jurisdiction_id, rate_type,
    )
    if not row:
        return None, None
    pen = _parse_penalties(row["penalties"])
    penalty = None
    if pen:
        penalty = RiskPenalty(
            civil_min=pen.get("civil_penalty_min"),
            civil_max=pen.get("civil_penalty_max"),
            per_violation=pen.get("per_violation"),
            annual_cap=pen.get("annual_cap"),
            enforcing_agency=pen.get("enforcing_agency"),
            summary=pen.get("summary"),
        )
    return penalty, row["statute_citation"]


async def get_compliance_risk_summary(company_id: UUID) -> ComplianceRiskSummary:
    issues: list[RiskIssue] = []
    get_ahead: list[RiskGetAhead] = []
    # Per-issue "basis": the raw values that define the violation. Drives the
    # dismissed-issue re-surface rule + the "before" value in the trail.
    basis_by_key: dict = {}
    today = date.today()

    features = {}
    try:
        features = await get_company_features(company_id)
    except Exception:
        logger.exception("risk-summary: feature fetch failed for %s", company_id)

    async with get_connection() as conn:
        locations = await conn.fetch(
            "SELECT id, name, city, state, jurisdiction_id FROM business_locations WHERE company_id = $1",
            company_id,
        )
        loc_by_id = {loc["id"]: loc for loc in locations}

        # 1. WAGE — per-location, statutory violations (always critical).
        try:
            for loc in locations:
                impact = await get_employee_impact_for_location(loc["id"], company_id)
                by_rate = impact.get("violations_by_rate_type") or {}
                for rate_type, violations in by_rate.items():
                    penalty, citation = await _wage_penalty_for_location(
                        conn, loc["jurisdiction_id"], rate_type
                    )
                    is_hourly = rate_type == "general"
                    for v in violations:
                        name = v["employee_name"]
                        rate, threshold = v["pay_rate"], v["threshold"]
                        if is_hourly:
                            detail = f"Paid ${rate:,.2f}/hr — the applicable minimum is ${threshold:,.2f}/hr."
                            rec = f"Raise {name}'s hourly rate to ${threshold:,.2f}/hr, or correct the classification."
                        else:
                            detail = (
                                f"Exempt salary ${rate:,.0f}/yr is below the ${threshold:,.0f}/yr threshold."
                            )
                            rec = (
                                f"Raise {name}'s salary to ${threshold:,.0f}/yr or reclassify as non-exempt (overtime-eligible)."
                            )
                        key = f"wage:{v['employee_id']}:{rate_type}"
                        basis_by_key[key] = {"pay_rate": float(rate), "threshold": float(threshold)}
                        issues.append(RiskIssue(
                            id=key,
                            source="wage",
                            severity="critical",
                            title=f"{name} paid below the applicable minimum",
                            detail=detail,
                            employee_names=[name],
                            location_label=_loc_label(loc),
                            penalty=penalty,
                            statute_citation=citation,
                            recommendation=rec,
                            link=f"/app/employees/{v['employee_id']}?tab=profile&edit=1",
                        ))
        except Exception:
            logger.exception("risk-summary: wage section failed for %s", company_id)

        # 2. CREDENTIALS — company-scoped expiry (gated on credential_templates).
        if features.get("credential_templates"):
            try:
                rows = await conn.fetch(
                    """
                    SELECT e.id AS employee_id,
                           e.first_name || ' ' || e.last_name AS employee_name,
                           e.job_title, x.credential_type, x.expiry_date
                    FROM employees e
                    JOIN employee_credentials ec ON ec.employee_id = e.id
                    CROSS JOIN LATERAL (VALUES
                        ('medical_license',       ec.license_expiration),
                        ('dea_registration',      ec.dea_expiration),
                        ('board_certification',   ec.board_certification_expiration),
                        ('malpractice_insurance', ec.malpractice_expiration)
                    ) AS x(credential_type, expiry_date)
                    WHERE e.org_id = $1
                      AND e.termination_date IS NULL
                      AND x.expiry_date IS NOT NULL
                      AND x.expiry_date <= CURRENT_DATE + INTERVAL '90 days'
                    ORDER BY x.expiry_date ASC
                    """,
                    company_id,
                )
                for r in rows:
                    exp = r["expiry_date"]
                    days = (exp - today).days
                    label = _CREDENTIAL_LABELS.get(r["credential_type"], r["credential_type"])
                    name = r["employee_name"]
                    if days < 0:
                        severity = "critical"
                        detail = f"{label} expired {exp.isoformat()} ({-days} day{'s' if -days != 1 else ''} ago)."
                        rec = f"Renew {name}'s {label} immediately — it lapsed and must be restored before their next shift."
                    elif days <= 30:
                        severity = "high"
                        detail = f"{label} expires {exp.isoformat()} (in {days} day{'s' if days != 1 else ''})."
                        rec = f"Start {name}'s {label} renewal now — it expires within 30 days."
                    else:
                        severity = "moderate"
                        detail = f"{label} expires {exp.isoformat()} (in {days} days)."
                        rec = f"Schedule {name}'s {label} renewal — expires within 90 days."
                    key = f"credential:{r['employee_id']}:{r['credential_type']}"
                    basis_by_key[key] = {"expiry": exp.isoformat()}
                    issues.append(RiskIssue(
                        id=key,
                        source="credential",
                        severity=severity,
                        title=f"{name} — {label} {'expired' if days < 0 else 'expiring'}",
                        detail=detail,
                        employee_names=[name],
                        location_label=r["job_title"],
                        recommendation=rec,
                        link=f"/app/employees/{r['employee_id']}?tab=credentials",
                        deadline=exp.isoformat(),
                    ))
            except Exception:
                logger.exception("risk-summary: credential section failed for %s", company_id)

        # 3. INCIDENTS — open safety/behavioral incidents (gated on incidents).
        if features.get("incidents"):
            try:
                rows = await conn.fetch(
                    """
                    SELECT id, incident_number, title, severity, status,
                           occurred_at, osha_recordable, location_id, location
                    FROM ir_incidents
                    WHERE company_id = $1 AND status = ANY($2::text[])
                    ORDER BY occurred_at DESC
                    """,
                    company_id, list(_OPEN_INCIDENT_STATUSES),
                )
                for r in rows:
                    sev = "critical" if r["severity"] == "critical" else (
                        "high" if r["severity"] == "high" else "moderate")
                    num = r["incident_number"] or "incident"
                    loc = loc_by_id.get(r["location_id"])
                    label = _loc_label(loc) if loc else r["location"]
                    if r["osha_recordable"] is None:
                        rec = f"Determine OSHA recordability for {num} and complete the investigation before the 300A deadline."
                    else:
                        rec = f"Investigate and resolve {num}; assign corrective actions and close it out."
                    key = f"incident:{r['id']}"
                    basis_by_key[key] = {"status": r["status"], "severity": r["severity"]}
                    issues.append(RiskIssue(
                        id=key,
                        source="incident",
                        severity=sev,
                        title=r["title"] or num,
                        detail=(
                            f"Open {r['severity']} {num}"
                            + (" · OSHA recordability not yet determined" if r["osha_recordable"] is None else "")
                        ),
                        location_label=label,
                        recommendation=rec,
                        link=f"/app/ir/{r['id']}",
                        deadline=r["occurred_at"].date().isoformat() if r["occurred_at"] else None,
                    ))
            except Exception:
                logger.exception("risk-summary: incident section failed for %s", company_id)

        # 4. CRITICAL ALERTS — unread + critical compliance alerts (remediable
        #    in-page via the action-plan endpoint).
        try:
            rows = await conn.fetch(
                """
                SELECT ca.id, ca.title, ca.message, ca.severity, ca.action_required,
                       ca.deadline, ca.affected_employee_count, ca.location_id
                FROM compliance_alerts ca
                WHERE ca.company_id = $1 AND ca.status = 'unread' AND ca.severity = 'critical'
                ORDER BY ca.deadline ASC NULLS LAST, ca.created_at DESC
                """,
                company_id,
            )
            for r in rows:
                loc = loc_by_id.get(r["location_id"])
                key = f"alert:{r['id']}"
                basis_by_key[key] = {
                    "deadline": r["deadline"].isoformat() if r["deadline"] else None,
                    "severity": r["severity"],
                }
                issues.append(RiskIssue(
                    id=key,
                    source="alert",
                    severity="critical",
                    title=r["title"] or "Critical compliance alert",
                    detail=r["message"],
                    employee_names=[],
                    location_label=_loc_label(loc) if loc else None,
                    recommendation=r["action_required"],
                    link=None,  # in-page → Alerts tab
                    deadline=r["deadline"].isoformat() if r["deadline"] else None,
                    alert_id=str(r["id"]),
                ))
        except Exception:
            logger.exception("risk-summary: alert section failed for %s", company_id)

        # 5. GET-AHEAD — upcoming legislation + alert deadlines with lead time.
        try:
            leg_rows = await conn.fetch(
                """
                SELECT ul.title, ul.expected_effective_date, ul.category,
                       bl.name AS location_name, bl.city, bl.state
                FROM upcoming_legislation ul
                JOIN business_locations bl ON ul.location_id = bl.id
                WHERE ul.company_id = $1
                  AND ul.current_status NOT IN ('effective', 'dismissed')
                  AND ul.expected_effective_date IS NOT NULL
                  AND ul.expected_effective_date > CURRENT_DATE
                ORDER BY ul.expected_effective_date ASC
                LIMIT 6
                """,
                company_id,
            )
            for r in leg_rows:
                eff = r["expected_effective_date"]
                get_ahead.append(RiskGetAhead(
                    title=r["title"],
                    kind="legislation",
                    effective_date=eff.isoformat(),
                    days_until=(eff - today).days,
                    location_label=r["location_name"] or (f"{r['city']}, {r['state']}" if r["city"] else None),
                ))
        except Exception:
            logger.exception("risk-summary: get-ahead section failed for %s", company_id)

        # ── Remediation lifecycle: persist state, auto-document resolved,
        #    suppress dismissed. Must run with conn while issues are complete.
        recently_resolved: list = []
        dismissed_count = 0
        current_keys = {i.id for i in issues}
        try:
            state_map = await reconcile_issue_state(conn, company_id, issues, basis_by_key)
            dismissed_keys = {k for k, r in state_map.items() if r["status"] == "dismissed"}
            # dismissed AND still produced by the live check = hidden-but-real
            dismissed_count = len(dismissed_keys & current_keys)
            issues = [i for i in issues if i.id not in dismissed_keys]
            for i in issues:
                st = state_map.get(i.id)
                if st and st["first_seen_at"]:
                    i.first_seen_at = st["first_seen_at"].isoformat()
            recently_resolved = await fetch_recent_remediations(conn, company_id, days=30)
        except Exception:
            logger.exception("risk-summary: remediation reconcile failed for %s", company_id)

    # Recompute affected employees from the SURVIVING issues (post-dismissal),
    # keyed on the employee id embedded in the wage/credential issue key.
    affected_ids = set()
    for i in issues:
        if i.source in ("wage", "credential"):
            parts = i.id.split(":")
            if len(parts) >= 2:
                affected_ids.add(parts[1])

    # Also surface alert deadlines that are in the future as get-ahead items.
    for iss in issues:
        if iss.source == "alert" and iss.deadline:
            try:
                d = date.fromisoformat(iss.deadline)
            except ValueError:
                continue
            if d > today:
                get_ahead.append(RiskGetAhead(
                    title=iss.title,
                    kind="deadline",
                    effective_date=iss.deadline,
                    days_until=(d - today).days,
                    location_label=iss.location_label,
                ))

    get_ahead.sort(key=lambda g: (g.days_until if g.days_until is not None else 10**9))

    # ── Posture roll-up ──
    open_critical = sum(1 for i in issues if i.severity == "critical")
    open_high = sum(1 for i in issues if i.severity == "high")
    open_moderate = sum(1 for i in issues if i.severity == "moderate")

    exposure_min = 0.0
    exposure_max = 0.0
    unquantified = 0
    for i in issues:
        if not i.penalty:
            continue
        cmin, cmax = i.penalty.civil_min, i.penalty.civil_max
        if cmin is None and cmax is None:
            unquantified += 1
        else:
            # A statute may set a $0 floor ("up to $X") — treat 0 as a real
            # bound, never as "missing" (a falsy 0 would borrow the max).
            lo = cmin if cmin is not None else cmax
            hi = cmax if cmax is not None else cmin
            exposure_min += lo or 0
            exposure_max += hi or 0

    # Next deadline = the soonest UPCOMING date across everything that carries
    # one — credential/incident/alert issues AND the get-ahead lane — not just
    # legislation. A license expiring tomorrow must win this cell.
    next_days: int | None = None
    next_label: str | None = None
    _best = None  # (days_until, label)
    for g in get_ahead:
        if g.days_until is not None and g.days_until >= 0:
            if _best is None or g.days_until < _best[0]:
                _best = (g.days_until, g.title)
    for i in issues:
        if not i.deadline:
            continue
        try:
            d = (date.fromisoformat(i.deadline) - today).days
        except ValueError:
            continue
        if d >= 0 and (_best is None or d < _best[0]):
            _best = (d, i.title)
    if _best is not None:
        next_days, next_label = _best

    issues.sort(key=lambda i: (
        _SEV_RANK.get(i.severity, 9),
        i.deadline or "9999-12-31",
    ))

    posture = RiskPosture(
        open_critical=open_critical,
        open_high=open_high,
        open_moderate=open_moderate,
        employees_affected=len(affected_ids),
        exposure_min_usd=round(exposure_min, 2),
        exposure_max_usd=round(exposure_max, 2),
        exposure_unquantified_count=unquantified,
        next_deadline_days=next_days,
        next_deadline_label=next_label,
    )

    return ComplianceRiskSummary(
        posture=posture,
        issues=issues,
        get_ahead=get_ahead,
        recently_resolved=recently_resolved,
        dismissed_count=dismissed_count,
        generated_at=datetime.utcnow().isoformat(),
    )
