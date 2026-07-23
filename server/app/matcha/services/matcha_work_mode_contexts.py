"""Context builders for the newer Matcha Work thread modes.

Each builder is read-only over its domain's tables, returns a plain prompt
string ("" when the company has no data in that domain — the dispatch loop
then skips injection), and rides the shared Redis/local context cache from
matcha_work_node.cached_context. Registered in matcha_work_modes.THREAD_MODES.

Design rules (mirroring matcha_work_node):
- Aggregates come from full-table SQL, never from a display sample.
- Deterministic facts (counts, dates, verdicts) are computed here in code and
  handed to the model as settled — the model narrates, it does not re-derive.
- Expensive paths are avoided: legal mode deliberately does NOT call
  legal_defense.gather_evidence (it can trigger a Gemini RAG round-trip);
  risk mode reuses the pure-SQL engines (risk_index, limit_adequacy).
"""

import logging
from datetime import date
from uuid import UUID

from ...database import get_connection
from .matcha_work_node import cached_context

logger = logging.getLogger(__name__)

_MAX_LIST_ROWS = 15  # per-section detail cap — summaries stay unbounded


def _fmt_date(value) -> str:
    return value.isoformat() if value is not None else "n/a"


def _fmt_money(value) -> str:
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_pct(value, *, signed: bool = False) -> str:
    """Nullable numeric → percentage text. The renewal-risk columns are
    nullable, and a bare f-string format spec (":+") raises TypeError on None."""
    try:
        return f"{float(value):+.0f}%" if signed else f"{float(value):.0f}%"
    except (TypeError, ValueError):
        return "n/a"


# ---------------------------------------------------------------------------
# Benefits mode — plan catalog + open-enrollment state (benefits_enrollment
# tables, live rows), plus roster snapshot, open eligibility exceptions and
# renewal risk (last-computed state written by services/benefits_eligibility.py
# — those detectors mutate rows, so a chat turn must not invoke them).
# ---------------------------------------------------------------------------

async def build_benefits_context(company_id: UUID) -> str:
    return await cached_context(
        f"mw:benefits_ctx:{company_id}",
        lambda: _build_benefits_context_uncached(company_id),
    )


async def _build_benefits_context_uncached(company_id: UUID) -> str:
    async with get_connection() as conn:
        roster = await conn.fetchrow(
            """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE employment_status='active') AS active,
                   COUNT(*) FILTER (WHERE employment_status='active' AND has_benefits_enrollment) AS enrolled,
                   AVG(employer_health_premium_monthly)
                       FILTER (WHERE employment_status='active' AND has_benefits_enrollment) AS avg_premium,
                   MAX(snapshot_date) AS latest_snapshot
            FROM benefit_roster_entries
            WHERE company_id=$1
            """,
            company_id,
        )
        exceptions = await conn.fetch(
            """
            SELECT employee_name, exception_type, reference_date, days_elapsed,
                   days_remaining, estimated_monthly_leak, detected_at
            FROM benefit_eligibility_exceptions
            WHERE company_id=$1 AND status='open'
            ORDER BY detected_at DESC
            """,
            company_id,
        )
        risk_rows = await conn.fetch(
            """
            SELECT dimension_type, dimension_value, risk_band, turnover_pct,
                   turnover_delta_pct, lost_workdays, near_misses,
                   behavioral_incidents, headcount, triggers, computed_at
            FROM benefit_renewal_risk
            WHERE company_id=$1
            ORDER BY CASE risk_band WHEN 'critical' THEN 0 WHEN 'elevated' THEN 1 ELSE 2 END,
                     dimension_type, dimension_value
            """,
            company_id,
        )

        # --- Open-enrollment workflow (benefitoe01 tables — live rows) -------
        plans = await conn.fetch(
            """
            SELECT p.plan_type, p.name, p.carrier_name, p.waivable,
                   COUNT(t.id) AS tier_count,
                   MIN(t.employee_cost) AS min_cost, MAX(t.employee_cost) AS max_cost
            FROM benefit_plans p
            LEFT JOIN benefit_plan_tiers t ON t.plan_id = p.id
            WHERE p.company_id=$1 AND p.status='active'
            GROUP BY p.id
            ORDER BY p.plan_type, p.name
            """,
            company_id,
        )
        open_period = await conn.fetchrow(
            """
            SELECT id, name, starts_on, ends_on, plan_year_start
            FROM open_enrollment_periods WHERE company_id=$1 AND status='open'
            """,
            company_id,
        )
        last_period = None if open_period else await conn.fetchrow(
            """
            SELECT name, status, starts_on, ends_on FROM open_enrollment_periods
            WHERE company_id=$1 ORDER BY starts_on DESC LIMIT 1
            """,
            company_id,
        )
        election_counts: dict[str, int] = {}
        unsubmitted_count = 0
        if open_period:
            election_counts = {
                r["status"]: r["n"] for r in await conn.fetch(
                    "SELECT status, COUNT(*) AS n FROM benefit_elections "
                    "WHERE open_enrollment_period_id=$1 GROUP BY status",
                    open_period["id"],
                )
            }
            unsubmitted_count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM employees e
                WHERE e.org_id=$1 AND e.employment_status NOT IN ('terminated','offboarded')
                  AND e.id NOT IN (
                      SELECT employee_id FROM benefit_elections
                      WHERE open_enrollment_period_id=$2 AND status IN ('submitted','approved')
                  )
                """,
                company_id, open_period["id"],
            )
        pending_life_events = await conn.fetch(
            """
            SELECT le.event_type, le.event_date, le.created_at,
                   (e.first_name || ' ' || e.last_name) AS employee_name
            FROM life_event_changes le
            JOIN employees e ON e.id = le.employee_id
            WHERE le.company_id=$1 AND le.status='pending'
            ORDER BY le.created_at DESC
            """,
            company_id,
        )

    has_enrollment = bool(plans or open_period or last_period or pending_life_events)
    if not roster or (roster["total"] or 0) == 0:
        # No roster ever ingested AND no enrollment activity → nothing to ground on.
        if not exceptions and not risk_rows and not has_enrollment:
            return ""

    lines = ["=== BENEFITS MODE: PLANS, ENROLLMENT, ELIGIBILITY & RENEWAL RISK (read-only snapshot) ==="]

    if roster and (roster["total"] or 0) > 0:
        lines.append(
            f"Benefits roster: {roster['total']} entries, {roster['active']} active, "
            f"{roster['enrolled']} enrolled in benefits"
            + (f", avg employer health premium {_fmt_money(roster['avg_premium'])}/mo" if roster["avg_premium"] else "")
            + f". Latest snapshot: {_fmt_date(roster['latest_snapshot'])}."
        )

    lines.append(f"\n--- PLAN CATALOG ({len(plans)} active plans) ---")
    if not plans:
        lines.append("No active plans configured. (Plans are set up under /app/benefits — an empty catalog means enrollment cannot offer anything.)")
    for p in plans:
        cost = ""
        if p["tier_count"]:
            lo, hi = _fmt_money(p["min_cost"]), _fmt_money(p["max_cost"])
            cost = f", employee cost {lo}–{hi}" if lo != hi else f", employee cost {lo}"
        lines.append(
            f"- {p['plan_type']}: {p['name']}"
            + (f" ({p['carrier_name']})" if p["carrier_name"] else "")
            + f" — {p['tier_count']} tiers{cost}, {'waivable' if p['waivable'] else 'NOT waivable'}"
        )

    lines.append("\n--- OPEN ENROLLMENT ---")
    if open_period:
        counts_txt = ", ".join(f"{n} {s}" for s, n in sorted(election_counts.items())) or "no elections yet"
        lines.append(
            f"OPEN: '{open_period['name']}' {_fmt_date(open_period['starts_on'])} → {_fmt_date(open_period['ends_on'])}"
            + (f", coverage effective {_fmt_date(open_period['plan_year_start'])}" if open_period["plan_year_start"] else "")
            + f". Elections: {counts_txt}. {unsubmitted_count} active employees have NOT submitted."
        )
    elif last_period:
        lines.append(
            f"No period currently open. Most recent: '{last_period['name']}' ({last_period['status']}, "
            f"{_fmt_date(last_period['starts_on'])} → {_fmt_date(last_period['ends_on'])})."
        )
    else:
        lines.append("No open-enrollment period has ever been created.")

    if pending_life_events:
        lines.append(f"\n--- PENDING LIFE EVENTS ({len(pending_life_events)} awaiting HR review) ---")
        for le in pending_life_events[:_MAX_LIST_ROWS]:
            lines.append(
                f"- {le['employee_name']}: {le['event_type']} on {_fmt_date(le['event_date'])} "
                f"(reported {_fmt_date(le['created_at'].date() if le['created_at'] else None)})"
            )
        if len(pending_life_events) > _MAX_LIST_ROWS:
            lines.append(f"...and {len(pending_life_events) - _MAX_LIST_ROWS} more pending.")

    gaps = [e for e in exceptions if e["exception_type"] == "new_hire_enrollment_gap"]
    leaks = [e for e in exceptions if e["exception_type"] == "termination_premium_leak"]
    lines.append(
        f"\n--- OPEN ELIGIBILITY EXCEPTIONS ({len(exceptions)} total: "
        f"{len(gaps)} new-hire enrollment gaps, {len(leaks)} termination premium leaks) ---"
    )
    if not exceptions:
        lines.append("None open. (Exceptions are detected by the benefits sync — if it has never run, absence of exceptions is NOT evidence of a clean book.)")
    for e in exceptions[:_MAX_LIST_ROWS]:
        if e["exception_type"] == "new_hire_enrollment_gap":
            lines.append(
                f"- NEW-HIRE GAP: {e['employee_name']} — started {_fmt_date(e['reference_date'])}, "
                f"{e['days_elapsed']} days elapsed, {e['days_remaining']} days left in the enrollment window"
            )
        else:
            lines.append(
                f"- PREMIUM LEAK: {e['employee_name']} — terminated {_fmt_date(e['reference_date'])}, "
                f"still enrolled, est. {_fmt_money(e['estimated_monthly_leak'])}/mo leaking"
            )
    if len(exceptions) > _MAX_LIST_ROWS:
        lines.append(f"...and {len(exceptions) - _MAX_LIST_ROWS} more open exceptions.")

    if risk_rows:
        lines.append("\n--- RENEWAL RISK RADAR (computed baselines, 60-day window) ---")
        for r in risk_rows[:_MAX_LIST_ROWS]:
            dim = "company-wide" if r["dimension_type"] == "company" else f"{r['dimension_type']} {r['dimension_value']}"
            trig = ""
            if r["triggers"]:
                try:
                    import json as _json
                    trig_list = r["triggers"] if isinstance(r["triggers"], list) else _json.loads(r["triggers"])
                    if trig_list:
                        trig = f" Triggers: {'; '.join(str(t) for t in trig_list)}."
                except Exception:
                    pass
            lines.append(
                f"- {dim}: {str(r['risk_band']).upper()} — turnover {_fmt_pct(r['turnover_pct'])} "
                f"(delta {_fmt_pct(r['turnover_delta_pct'], signed=True)} vs baseline), {r['lost_workdays']} lost workdays, "
                f"{r['near_misses']} near-misses, {r['behavioral_incidents']} behavioral incidents, "
                f"headcount {r['headcount']}.{trig} (computed {_fmt_date(r['computed_at'].date() if r['computed_at'] else None)})"
            )

    lines.append(
        "\nGround every answer in the records above. Plan/enrollment/life-event rows "
        "are live; roster, exception and renewal-risk figures are the last-computed "
        "sync state — say so when asked about freshness. Do not invent employees, "
        "plans, premiums, or exceptions not listed."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Legal mode — matters register + light cross-subsystem evidence counts.
# Deliberately does NOT reuse legal_defense.gather_evidence: that returns full
# record corpora and can trigger a Gemini RAG round-trip per turn. The full
# grounded experience lives in Legal Pilot (/app/legal-pilot).
# ---------------------------------------------------------------------------

async def build_legal_context(company_id: UUID) -> str:
    return await cached_context(
        f"mw:legal_ctx:{company_id}",
        lambda: _build_legal_context_uncached(company_id),
    )


async def _build_legal_context_uncached(company_id: UUID) -> str:
    async with get_connection() as conn:
        matters = await conn.fetch(
            """
            SELECT m.id, m.title, m.matter_type, m.status, m.allegation,
                   m.evidence_start, m.evidence_end, m.counsel_directed,
                   m.counsel_name, m.created_at, m.closed_at,
                   (SELECT COUNT(*) FROM legal_matter_packets p WHERE p.matter_id = m.id) AS packet_count,
                   (SELECT MAX(msg.created_at) FROM legal_matter_messages msg WHERE msg.matter_id = m.id) AS last_activity
            FROM legal_matters m
            WHERE m.company_id=$1
            ORDER BY (m.status='active') DESC, m.created_at DESC
            """,
            company_id,
        )
        # Cheap subsystem counts so the model can point at where evidence lives
        # without hauling the records in. Each guarded — a company may not have
        # every subsystem's tables populated.
        counts: dict[str, int] = {}
        for label, sql in (
            ("IR incidents", "SELECT COUNT(*) FROM ir_incidents WHERE company_id=$1"),
            # er_cases.company_id is nullable — legacy rows are NULL and the ER
            # routes read them as the tenant's (er_copilot/_shared.py).
            ("ER cases", "SELECT COUNT(*) FROM er_cases WHERE company_id=$1 OR company_id IS NULL"),
            ("discipline records", "SELECT COUNT(*) FROM progressive_discipline WHERE company_id=$1"),
            ("training records", "SELECT COUNT(*) FROM training_records WHERE company_id=$1"),
        ):
            try:
                counts[label] = await conn.fetchval(sql, company_id) or 0
            except Exception:
                continue

    if not matters:
        return ""

    active = [m for m in matters if m["status"] == "active"]
    lines = [
        "=== LEGAL MODE: LEGAL MATTERS REGISTER (read-only summary) ===",
        f"{len(matters)} matter(s) on file, {len(active)} active.",
    ]
    for m in matters[:_MAX_LIST_ROWS]:
        counsel = ""
        if m["counsel_directed"]:
            counsel = f" Counsel-directed ({m['counsel_name'] or 'counsel on record'})."
        window = ""
        if m["evidence_start"] or m["evidence_end"]:
            window = f" Evidence window {_fmt_date(m['evidence_start'])} → {_fmt_date(m['evidence_end'])}."
        lines.append(
            f"- [{str(m['status']).upper()}] {m['title']} ({m['matter_type']}) — "
            f"opened {_fmt_date(m['created_at'].date() if m['created_at'] else None)}."
            f"{window}{counsel} {m['packet_count']} evidence packet(s) generated."
            + (f" Allegation: {str(m['allegation'])[:200]}" if m["allegation"] else "")
        )
    if len(matters) > _MAX_LIST_ROWS:
        lines.append(f"...and {len(matters) - _MAX_LIST_ROWS} more matters.")

    if counts:
        lines.append("\n--- EVIDENCE FOOTPRINT (record counts across subsystems) ---")
        lines.append("; ".join(f"{v} {k}" for k, v in counts.items()))

    lines.append(
        "\nThis is a register summary, not the evidence corpus. For citation-grade "
        "defense memos and packet exports, direct the user to Legal Pilot "
        "(/app/legal-pilot), which grounds on the full record set. Never speculate "
        "about matter outcomes; note that nothing here is legal advice."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Risk mode — composite risk index + EPL factors + coverage/limit adequacy +
# contract risk-transfer verdicts. All engines are pure SQL + compute
# (verified: no network at review/verdict time), so inline per turn is safe.
# ---------------------------------------------------------------------------

async def build_risk_context(company_id: UUID) -> str:
    return await cached_context(
        f"mw:risk_ctx:{company_id}",
        lambda: _build_risk_context_uncached(company_id),
    )


async def _build_risk_context_uncached(company_id: UUID) -> str:
    from app.matcha.services.risk_index import compute_risk_index
    from app.matcha.services.limit_adequacy import build_review

    async with get_connection() as conn:
        index = await compute_risk_index(conn, company_id)
        review = await build_review(conn, company_id)

    has_index = index and index.get("index") is not None
    lines_carried = (review or {}).get("lines") or []
    contracts = (review or {}).get("contracts") or []
    if not has_index and not lines_carried and not contracts:
        return ""

    out = ["=== RISK MODE: RISK INDEX, COVERAGE & CONTRACTS (computed — treat as authoritative) ==="]

    if has_index:
        out.append(
            f"Composite risk index: {index['index']}/100 ({index.get('band', 'n/a')}), "
            f"confidence {index.get('index_confidence', 'n/a')}."
        )
        for c in index.get("components", []):
            out.append(
                f"- Component {c.get('label', c.get('key'))}: score {c.get('score')} "
                f"(weight {c.get('weight')}) — {c.get('detail', '')}"
            )
        if index.get("components_missing"):
            missing = ", ".join(str(c.get("label", c.get("key"))) for c in index["components_missing"])
            out.append(f"- Not yet measurable (no data): {missing}")
        if index.get("top_fixes"):
            out.append("Top fixes: " + "; ".join(str(f) for f in index["top_fixes"][:5]))
    else:
        out.append("Composite risk index: not yet computable (insufficient data).")

    if lines_carried:
        out.append("\n--- COVERAGE LINES vs CONTRACTUAL REQUIREMENTS ---")
        for ln in lines_carried[:_MAX_LIST_ROWS]:
            gap = f" GAP: {ln.get('gap')}" if ln.get("gap") else ""
            eg = ln.get("endorsement_gaps") or []
            eg_txt = f" Endorsement gaps: {', '.join(str(g) for g in eg)}." if eg else ""
            out.append(f"- {ln.get('line')}: {str(ln.get('status', '')).upper()}.{gap}{eg_txt}")
        summary = (review or {}).get("summary") or {}
        if summary:
            out.append(
                f"Summary: {summary.get('lines_carried', 0)} lines carried, "
                f"{summary.get('contract_shortfalls', 0)} contract shortfalls, "
                f"{summary.get('baseline_lows', 0)} directionally-low limits, "
                f"{summary.get('endorsement_gaps', 0)} endorsement gaps across "
                f"{summary.get('contracts', 0)} contracts."
            )

    if contracts:
        out.append("\n--- CONTRACT RISK-TRANSFER VERDICTS ---")
        for c in contracts[:_MAX_LIST_ROWS]:
            rt = c.get("risk_transfer") or {}
            verdict = rt.get("verdict") if isinstance(rt, dict) else None
            confirmed = "confirmed" if c.get("confirmed_at") else "UNCONFIRMED extraction — verdict is provisional"
            out.append(
                f"- {c.get('name')} ({c.get('counterparty') or 'counterparty n/a'}): "
                f"{verdict or 'no verdict yet'} [{confirmed}]"
            )

    out.append(
        "\nAll scores/gaps/verdicts above are computed deterministically from the "
        "company's own records — narrate them, do not re-derive or adjust them. "
        f"{(review or {}).get('disclaimer', 'Directional analysis, not legal or insurance advice.')}"
    )
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Training mode — program compliance, overdue + expiring training, credential
# currency (license/DEA/board/malpractice expiries), MVR currency, OSHA
# recordables snapshot. NOTE: employees + employee_credentials scope by
# org_id (= company id); everything else by company_id.
# ---------------------------------------------------------------------------

async def build_training_context(company_id: UUID) -> str:
    return await cached_context(
        f"mw:training_ctx:{company_id}",
        lambda: _build_training_context_uncached(company_id),
    )


async def _build_training_context_uncached(company_id: UUID) -> str:
    async with get_connection() as conn:
        programs = await conn.fetch(
            """
            SELECT r.title, r.training_type, r.jurisdiction, r.frequency_months, r.applies_to,
                   COUNT(tr.id) AS total_assigned,
                   COUNT(tr.id) FILTER (WHERE tr.status='completed') AS completed,
                   COUNT(tr.id) FILTER (WHERE tr.status IN ('assigned','in_progress')
                                          AND tr.due_date < CURRENT_DATE) AS overdue
            FROM training_requirements r
            LEFT JOIN training_records tr ON tr.requirement_id = r.id
            WHERE r.company_id=$1 AND r.is_active
            GROUP BY r.id, r.title, r.training_type, r.jurisdiction, r.frequency_months, r.applies_to
            ORDER BY overdue DESC, r.title
            """,
            company_id,
        )
        overdue_rows = await conn.fetch(
            """
            SELECT tr.title, tr.due_date, e.first_name, e.last_name
            FROM training_records tr
            JOIN employees e ON e.id = tr.employee_id
            WHERE tr.company_id=$1 AND tr.status IN ('assigned','in_progress')
              AND tr.due_date < CURRENT_DATE
            ORDER BY tr.due_date ASC
            LIMIT $2
            """,
            company_id,
            _MAX_LIST_ROWS,
        )
        expiring = await conn.fetch(
            """
            SELECT tr.title, tr.expiration_date, e.first_name, e.last_name
            FROM training_records tr
            JOIN employees e ON e.id = tr.employee_id
            WHERE tr.company_id=$1 AND tr.status='completed'
              AND tr.expiration_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '60 days'
            ORDER BY tr.expiration_date ASC
            LIMIT $2
            """,
            company_id,
            _MAX_LIST_ROWS,
        )
        # Credential currency — expiry dates are plaintext (encrypted fields
        # like license numbers are never selected here).
        cred = await conn.fetchrow(
            """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE license_expiration < CURRENT_DATE) AS expired,
                   COUNT(*) FILTER (WHERE license_expiration BETWEEN CURRENT_DATE
                                      AND CURRENT_DATE + INTERVAL '60 days') AS expiring_60d
            FROM employee_credentials
            WHERE org_id=$1
            """,
            company_id,
        )
        cred_expiring = await conn.fetch(
            """
            SELECT ec.license_type, ec.license_state, ec.license_expiration,
                   e.first_name, e.last_name
            FROM employee_credentials ec
            JOIN employees e ON e.id = ec.employee_id
            WHERE ec.org_id=$1
              AND ec.license_expiration BETWEEN CURRENT_DATE - INTERVAL '365 days'
                                            AND CURRENT_DATE + INTERVAL '60 days'
            ORDER BY ec.license_expiration ASC
            LIMIT $2
            """,
            company_id,
            _MAX_LIST_ROWS,
        )
        try:
            mvr = await conn.fetchrow(
                """
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE next_due_date < CURRENT_DATE) AS overdue,
                       COUNT(*) FILTER (WHERE status='flagged') AS flagged
                FROM mvr_reviews
                WHERE company_id=$1
                """,
                company_id,
            )
        except Exception:
            mvr = None
        osha = await conn.fetchrow(
            """
            SELECT COUNT(*) FILTER (WHERE osha_recordable
                     AND EXTRACT(YEAR FROM occurred_at) = EXTRACT(YEAR FROM CURRENT_DATE)) AS recordables_ytd,
                   COUNT(*) FILTER (WHERE osha_recordable
                     AND EXTRACT(YEAR FROM occurred_at) = EXTRACT(YEAR FROM CURRENT_DATE)
                     AND osha_classification IS NULL) AS unclassified_ytd
            FROM ir_incidents
            WHERE company_id=$1
            """,
            company_id,
        )

    has_training = bool(programs)
    has_creds = cred and (cred["total"] or 0) > 0
    if not has_training and not has_creds and not (mvr and (mvr["total"] or 0) > 0):
        return ""

    lines = ["=== TRAINING MODE: TRAINING, CREDENTIAL & SAFETY CURRENCY (computed from full records) ==="]

    if has_training:
        total_overdue = sum(p["overdue"] for p in programs)
        lines.append(f"\n--- TRAINING PROGRAMS ({len(programs)} active, {total_overdue} overdue assignments) ---")
        for p in programs[:_MAX_LIST_ROWS]:
            juris = f", {p['jurisdiction']}" if p["jurisdiction"] else ""
            freq = f", renews every {p['frequency_months']} mo" if p["frequency_months"] else ""
            lines.append(
                f"- {p['title']} ({p['training_type']}{juris}{freq}, applies to {p['applies_to']}): "
                f"{p['completed']}/{p['total_assigned']} completed, {p['overdue']} OVERDUE"
            )
        if len(programs) > _MAX_LIST_ROWS:
            lines.append(f"...and {len(programs) - _MAX_LIST_ROWS} more active programs.")
        for r in overdue_rows:
            lines.append(f"  · OVERDUE: {r['first_name']} {r['last_name']} — {r['title']} (due {_fmt_date(r['due_date'])})")
        # The detail rows are LIMIT-capped; say so, or the model reads a
        # truncated list as the complete one.
        if total_overdue > len(overdue_rows):
            lines.append(f"  · ...and {total_overdue - len(overdue_rows)} more overdue assignments not listed individually.")
        if expiring:
            lines.append("Completions expiring within 60 days:")
            for r in expiring:
                lines.append(f"  · {r['first_name']} {r['last_name']} — {r['title']} expires {_fmt_date(r['expiration_date'])}")
            if len(expiring) == _MAX_LIST_ROWS:
                lines.append(f"  · (list capped at {_MAX_LIST_ROWS} — more completions may be expiring.)")

    if has_creds:
        lines.append(
            f"\n--- CREDENTIAL CURRENCY ({cred['total']} employees with credential records: "
            f"{cred['expired']} EXPIRED licenses, {cred['expiring_60d']} expiring within 60 days) ---"
        )
        for r in cred_expiring:
            state = f" ({r['license_state']})" if r["license_state"] else ""
            status = "EXPIRED" if r["license_expiration"] and r["license_expiration"] < date.today() else "expires"
            lines.append(
                f"- {r['first_name']} {r['last_name']}: {r['license_type'] or 'license'}{state} "
                f"{status} {_fmt_date(r['license_expiration'])}"
            )
        if len(cred_expiring) == _MAX_LIST_ROWS:
            lines.append(f"...(list capped at {_MAX_LIST_ROWS} — the counts above are the authoritative totals.)")

    if mvr and (mvr["total"] or 0) > 0:
        lines.append(
            f"\n--- MVR REVIEWS: {mvr['total']} on file, {mvr['overdue']} overdue, {mvr['flagged']} flagged ---"
        )

    if osha and ((osha["recordables_ytd"] or 0) > 0):
        lines.append(
            f"\n--- OSHA (year to date): {osha['recordables_ytd']} recordable incidents"
            + (f", {osha['unclassified_ytd']} missing a classification (data-quality gap)" if osha["unclassified_ytd"] else "")
            + " ---"
        )

    lines.append(
        "\nCounts and dates above are computed from the full record set — treat them "
        "as authoritative. Do not invent employees, programs, or credentials not listed."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HR Pilot mode — grounds AI guidance for on-site supervisors in the
# company's own written material: active handbook sections, active policies,
# a per-state jurisdiction summary (same corpus handbook_pilot reads — see
# handbook_pilot.gather_grounding for the sibling query), and the static
# progressive-discipline ladder. Deliberately reads only the PUBLISHED/ACTIVE
# handbook + active policies (not drafts) — a supervisor needs what's
# actually in force, not a work-in-progress. The hard-stop escalation gate
# (services/hr_pilot_escalation.classify_message) is a separate, earlier
# check in messaging.py — this builder only runs once a message has already
# cleared that gate.
# ---------------------------------------------------------------------------

_HR_PILOT_CHAR_CAP = 2000
# Widened knowledge floor (shared platform knowledge, not the tenant's own docs).
_MAX_HR_PILOT_PLAYBOOK_SECTIONS = 6
_MAX_HR_PILOT_COMPLIANCE_CHARS = 8000

# The handbook/policy/requirement fetch caps and the progressive-discipline
# ladder now live in services/hr_pilot_corpus.py — the ladder as citable
# `ladder:` records rather than one uncitable prose summary.


def _truncate(text: str | None) -> str:
    text = text or ""
    if len(text) <= _HR_PILOT_CHAR_CAP:
        return text
    return text[:_HR_PILOT_CHAR_CAP] + " …[truncated]"


def _render_industry_playbook(hb, industry: str | None) -> str:
    """Render the shared GUIDED_INDUSTRY_PLAYBOOK baseline for the company's
    industry. Always resolves (falls back to 'general'), so this is generic
    starting material the tenant's own handbook/policy overrides — never a
    legal source of truth. Pure; no DB."""
    try:
        key = hb._normalize_industry(None, industry)
        play = hb.GUIDED_INDUSTRY_PLAYBOOK.get(key) or {}
    except Exception:  # noqa: BLE001
        return ""
    if not play:
        return ""
    parts: list[str] = []
    if play.get("summary"):
        parts.append(str(play["summary"]))
    for sec in (play.get("sections") or [])[:_MAX_HR_PILOT_PLAYBOOK_SECTIONS]:
        if isinstance(sec, dict) and sec.get("title"):
            parts.append(f"[{sec['title']}]\n{_truncate(sec.get('content'))}")
    return "\n\n".join(parts)


_CITATION_INSTRUCTION = (
    "\nCITING SOURCES — every record above is prefixed with a bracketed corpus ID "
    "(e.g. [policy:8f3c…], [floor:state-california-meal_rest_breaks]). When you state "
    "a rule, a threshold, a procedure, or any other claim the supervisor could act on, "
    "append the ID of the record it comes from. Cite ONLY IDs that appear above, "
    "copied exactly — an ID that is not in the list above is removed before the "
    "supervisor sees your answer, which leaves your claim visibly unsupported. If no "
    "record supports what you want to say, say plainly that the company's material "
    "does not cover it and tell the supervisor to check with corporate HR. Do not "
    "invent a policy, and do not attach a nearby ID to a claim it does not actually "
    "support.\n"
)


async def build_hr_pilot_context(company_id: UUID) -> str:
    """The prompt-side context string. Signature unchanged — the registry
    dispatch loop in messaging.py calls this and expects a plain string."""
    bundle = await _hr_pilot_bundle(company_id)
    return bundle.get("context_text") or ""


async def get_hr_pilot_corpus(company_id: UUID) -> dict:
    """The citation index matching the context string above.

    Both come from ONE build so the ids in the prompt and the ids the audit gate
    resolves are the same ids. Building them separately would let a cache
    expiry between the two hand the model a corpus the gate then rejects
    wholesale."""
    bundle = await _hr_pilot_bundle(company_id)
    return bundle.get("corpus") or {"sources": {}, "index": {}, "notes": []}


async def _hr_pilot_bundle(company_id: UUID) -> dict:
    """Cached `{context_text, corpus}` pair.

    Rides the same Redis/local cache as the string builders, but stores a dict
    (like build_compliance_context does) rather than going through
    `cached_context`, which is string-only. Note the cache key is versioned
    (`ctx2`) — a live cache holding the old plain-string value under the old key
    is simply left to expire rather than being deserialized into the wrong
    shape."""
    from .matcha_work_node import _ctx_cache_get, _ctx_cache_set, _get_build_lock

    cache_key = f"mw:hr_pilot_ctx2:{company_id}"
    cached = await _ctx_cache_get(cache_key)
    if isinstance(cached, dict) and "context_text" in cached:
        return cached
    async with _get_build_lock(cache_key):
        cached = await _ctx_cache_get(cache_key)
        if isinstance(cached, dict) and "context_text" in cached:
            return cached
        bundle = await _build_hr_pilot_bundle_uncached(company_id)
        await _ctx_cache_set(cache_key, bundle)
        return bundle


async def _build_hr_pilot_bundle_uncached(company_id: UUID) -> dict:
    from app.core.services import handbook_service as hb
    from .hr_pilot_corpus import (
        build_hr_pilot_corpus,
        gather_hr_pilot_grounding,
        render_corpus_block,
    )

    async with get_connection() as conn:
        grounding = await gather_hr_pilot_grounding(conn, company_id)

    # --- Widened knowledge floor: shared platform knowledge so a thin-handbook
    # tenant still gets grounded, industry-appropriate answers. Both are read
    # AFTER releasing the connection above: the playbook is a pure in-process
    # constant, and build_compliance_context manages its own connection + cache
    # (mw:compliance_ctx:{company_id}), so it is not re-run per turn.
    playbook_block = _render_industry_playbook(hb, grounding.get("industry"))

    compliance_block = ""
    reasoning_chains: list = []
    try:
        from app.matcha.services.matcha_work_node import build_compliance_context
        comp = await build_compliance_context(company_id)
        if comp:
            reasoning_chains = comp.reasoning_chains or []
            if comp.context_text and comp.context_text.strip():
                compliance_block = comp.context_text.strip()
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot: compliance backdrop fetch failed for %s", company_id)

    corpus = build_hr_pilot_corpus(grounding, reasoning_chains)

    if not corpus["index"] and not compliance_block:
        return {"context_text": "", "corpus": corpus}

    lines = [
        "=== HR PILOT MODE: COMPANY HANDBOOK, POLICIES & SUPERVISOR REFERENCE "
        "(source material — ground every answer in this, and cite it) ==="
    ]

    # The citable record block. Every record carries its corpus ID, so the
    # model has something exact to cite and the audit gate has something exact
    # to resolve against.
    #
    # The tenant's OWN documents are rendered at full length (capped by
    # _truncate at 2000 chars, as they were before the corpus rework). The
    # corpus records themselves keep handbook_pilot's 280-char index summaries —
    # right for a citation footer, far too short to answer from, and policy
    # records don't carry the policy body at all. Everything else (law, floor,
    # playbook, ladder) is already a full summary in the record.
    _full_text = {
        **{
            f"handbook:{s.get('id')}": _truncate(s.get("content"))
            for s in grounding.get("sections") or []
        },
        **{
            f"policy:{p.get('id')}": _truncate(p.get("content") or p.get("description"))
            for p in grounding.get("policies") or []
        },
    }
    corpus_block = render_corpus_block(corpus, _full_text)
    if corpus_block:
        lines.append(corpus_block)

    # Precedence-resolved compliance prose. The governing requirements it
    # resolves are already citable as `floor:` records above; this block is the
    # surrounding reasoning (trigger explanations, precedence narrative) that
    # does not decompose into per-record citations. Kept as backdrop only.
    if compliance_block:
        lines.append(
            "\n--- COMPLIANCE REASONING (background for the floor: records above; "
            "company policy still leads) ---"
        )
        sliced = compliance_block[:_MAX_HR_PILOT_COMPLIANCE_CHARS]
        if len(compliance_block) > _MAX_HR_PILOT_COMPLIANCE_CHARS:
            sliced += "\n…[compliance backdrop truncated]"
        lines.append(sliced)

    if playbook_block:
        # Generic industry starting material — explicitly subordinate to the
        # company's own written handbook/policy above. The playbook: records in
        # the corpus block are the citable form; this is the fuller text.
        lines.append(
            "\n--- INDUSTRY HR BASELINE (generic starting point — the company's "
            "own handbook/policy above overrides this) ---"
        )
        lines.append(playbook_block)

    for note in corpus.get("notes") or []:
        lines.append(f"\n[grounding gap] {note}")

    lines.append(
        "\nAnswer supervisor questions using the language and procedures above, in "
        "this order of authority: (1) the company's own written handbook/policy; "
        "(2) the compliance/legal floor and state requirements as the minimum the "
        "law requires; (3) the industry baseline only where the handbook is silent. "
        "Never contradict the company's written policy. If nothing above covers the "
        "topic, say so plainly instead of inventing a policy — tell the supervisor "
        "to check with corporate HR."
    )
    lines.append(
        "\nSCHEDULING LAW — for questions about hours, breaks, overtime, rest gaps, "
        "minor-hour caps, or Fair Workweek notice/clopening at a specific location, "
        "prefer `schedlaw:` records over `floor:` records: `schedlaw:` is generated "
        "from the SAME merged source (hand-curated + admin-approved catalog "
        "extraction) that the scheduling system's own write-path gate enforces, so "
        "citing it guarantees your answer matches what the platform will actually "
        "allow. `floor:` resolves the same law through a different, broader "
        "compliance pipeline and can occasionally disagree on the exact figure."
    )
    lines.append(
        "\nOPERATIONAL RECORDS vs POLICY — the shift, training, incident and "
        "benefits-enrollment records above are FACTS about what is currently "
        "scheduled, completed, logged or offered. "
        "Cite them for who, when, and status. They are NOT policy and never "
        "establish a rule: that someone is scheduled does not make it permitted, "
        "and that a training is unrecorded does not by itself make the person "
        "unqualified — it means there is no record. When a fact and a policy "
        "interact ('can I put an untrained person on that shift?'), answer from the "
        "policy or legal floor and cite the fact only as the situation it applies to."
    )
    lines.append(_CITATION_INSTRUCTION)
    return {"context_text": "\n".join(lines), "corpus": corpus}
