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
# Benefits mode — roster snapshot, open eligibility exceptions, renewal risk.
# Reads the last-computed state written by services/benefits_eligibility.py
# (the detectors mutate rows, so a chat turn must not invoke them).
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

    if not roster or (roster["total"] or 0) == 0:
        # No roster ever ingested → nothing to ground on.
        if not exceptions and not risk_rows:
            return ""

    lines = ["=== BENEFITS MODE: ROSTER, ELIGIBILITY & RENEWAL RISK (read-only snapshot) ==="]

    if roster and (roster["total"] or 0) > 0:
        lines.append(
            f"Benefits roster: {roster['total']} entries, {roster['active']} active, "
            f"{roster['enrolled']} enrolled in benefits"
            + (f", avg employer health premium {_fmt_money(roster['avg_premium'])}/mo" if roster["avg_premium"] else "")
            + f". Latest snapshot: {_fmt_date(roster['latest_snapshot'])}."
        )

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
        "\nGround every answer in the records above. Figures are the last-computed "
        "sync state, not live — say so when asked about freshness. Do not invent "
        "employees, premiums, or exceptions not listed."
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

_MAX_HR_PILOT_SECTIONS = 60
_MAX_HR_PILOT_POLICIES = 60
_HR_PILOT_CHAR_CAP = 2000

_DISCIPLINE_LADDER_SUMMARY = (
    "Standard progressive-discipline steps: verbal warning -> written warning "
    "-> final warning -> termination review. A final warning already on file "
    "means the next step is a termination review — that is a hard-stop topic "
    "(see above): do not draft it here, route the supervisor to corporate HR."
)


def _truncate(text: str | None) -> str:
    text = text or ""
    if len(text) <= _HR_PILOT_CHAR_CAP:
        return text
    return text[:_HR_PILOT_CHAR_CAP] + " …[truncated]"


async def build_hr_pilot_context(company_id: UUID) -> str:
    return await cached_context(
        f"mw:hr_pilot_ctx:{company_id}",
        lambda: _build_hr_pilot_context_uncached(company_id),
    )


async def _build_hr_pilot_context_uncached(company_id: UUID) -> str:
    from app.core.services import handbook_service as hb

    sections: list = []
    policies: list = []
    requirements: dict = {}

    async with get_connection() as conn:
        try:
            sections = await conn.fetch(
                """
                SELECT hs.title, hs.section_type, hs.content, h.title AS handbook_title
                FROM handbook_sections hs
                JOIN handbook_versions hv ON hv.id = hs.handbook_version_id
                JOIN handbooks h ON h.id = hv.handbook_id
                WHERE h.company_id = $1 AND h.status = 'active'
                  AND hv.version_number = h.active_version
                ORDER BY hs.section_order
                LIMIT $2
                """,
                company_id, _MAX_HR_PILOT_SECTIONS,
            )
        except Exception:  # noqa: BLE001
            logger.warning("hr_pilot: handbook-section fetch failed for %s", company_id)

        try:
            policies = await conn.fetch(
                """
                SELECT title, category, content, description
                FROM policies
                WHERE company_id = $1 AND status = 'active'
                ORDER BY updated_at DESC
                LIMIT $2
                """,
                company_id, _MAX_HR_PILOT_POLICIES,
            )
        except Exception:  # noqa: BLE001
            logger.warning("hr_pilot: policy fetch failed for %s", company_id)

        try:
            scopes = await hb.derive_handbook_scopes_from_employees(conn, str(company_id))
            if scopes:
                requirements = await hb._fetch_state_requirements(conn, scopes)
        except Exception:  # noqa: BLE001
            logger.warning("hr_pilot: jurisdiction requirement fetch failed for %s", company_id)

    if not sections and not policies and not requirements:
        return ""

    lines = [
        "=== HR PILOT MODE: COMPANY HANDBOOK, POLICIES & SUPERVISOR REFERENCE "
        "(source material — ground every answer in this) ==="
    ]

    if sections:
        lines.append(f"\n--- ACTIVE HANDBOOK SECTIONS ({len(sections)}) ---")
        for s in sections:
            lines.append(f"\n[{s['handbook_title']} — {s['title']}]\n{_truncate(s['content'])}")

    if policies:
        lines.append(f"\n--- ACTIVE POLICIES ({len(policies)}) ---")
        for p in policies:
            label = f"{p['title']} ({p['category']})" if p["category"] else p["title"]
            body = p["content"] or p["description"] or ""
            lines.append(f"\n[{label}]\n{_truncate(body)}")

    if requirements:
        # Brief per-state backdrop only, not the full requirement text — HR
        # Pilot answers from written policy first; this keeps the model from
        # contradicting a state minimum the handbook is silent on.
        lines.append("\n--- APPLICABLE STATE REQUIREMENTS (backdrop — cite the handbook/policy language above first) ---")
        for state in sorted(requirements.keys()):
            reqs = requirements[state] or []
            if not reqs:
                continue
            lines.append(f"\n[{state}]")
            for r in reqs[:_MAX_LIST_ROWS]:
                title = r.get("title") or r.get("category") or "requirement"
                value = r.get("current_value")
                value_bit = f": {value}" if value else ""
                lines.append(f"  - {title}{value_bit}")
            if len(reqs) > _MAX_LIST_ROWS:
                lines.append(f"  - ...and {len(reqs) - _MAX_LIST_ROWS} more {state} requirements not listed individually.")

    lines.append(f"\n--- DISCIPLINE LADDER (company policy) ---\n{_DISCIPLINE_LADDER_SUMMARY}")

    lines.append(
        "\nAnswer supervisor questions using the language and procedures above. "
        "If the handbook/policies don't cover the topic, say so plainly instead "
        "of inventing a policy — tell the supervisor to check with corporate HR."
    )
    return "\n".join(lines)
