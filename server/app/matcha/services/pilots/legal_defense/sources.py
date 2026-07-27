"""Per-subsystem evidence sources — one query each, independently isolated.

Compact {cid, ref, summary, when} records feed the AI; full detail (IR/ER) is
pulled at packet time for the deterministic appendix (see details.py)."""

from ._shared import _dt, _emp_name, _hum, _hum_acronym, _iso, _money
from .theory import (
    _BROAD,
    _COMPLIANCE_CATEGORIES,
    _ER_CATEGORIES,
    _GENERIC_ER_CATEGORIES,
    _GENERIC_INFRACTIONS,
    _INCIDENT_TYPES,
    _INFRACTIONS,
    _demote_off_subject,
)


def _topic_filter(col: str, n: int) -> str:
    """Subject-matter predicate for a source's category/type column.
    ``$n`` = the theory's allowlist, ``$n+1`` = that column's known vocabulary.

    NULL allowlist → no filter. Otherwise a row survives when its value is in
    the allowlist, is NULL (unattributable — stays in), or lies outside the
    known vocabulary (company-defined slug — never silently dropped). An EMPTY
    allowlist therefore drops every row carrying a known-but-irrelevant value.

    Every filtered source uses this one predicate. The three hand-rolled
    variants it replaced differed only in whether they carried the NULL arm and
    the passthrough arm — and the next source to be added would have copied
    whichever was nearest. Both arms are inert on a column that is NOT NULL with
    a closed vocabulary, so uniformity costs nothing and a wrong copy costs a
    record silently missing from a legal corpus. The vocabulary must never be
    empty: ``NOT (col = ANY('{}'))`` is always true, degenerating the filter."""
    return (f" AND (${n}::text[] IS NULL OR {col} = ANY(${n})"
            f" OR {col} IS NULL OR NOT ({col} = ANY(${n + 1})))")


def _scope_direct(loc_col: str, state_col: str, n: int) -> str:
    """Matter-scope predicate for tables carrying their own location_id.
    ``$n`` = location uuid, ``$n+1`` = state. No scope → passes every row;
    location scope → exact match only; state-only scope → match on the joined
    location's state. Rows with no attributable location are excluded while a
    scope is active — deliberate, mirrors compliance_service.get_locations."""
    return (f" AND ((${n}::uuid IS NULL AND ${n + 1}::varchar IS NULL)"
            f" OR (${n}::uuid IS NOT NULL AND {loc_col} = ${n})"
            f" OR (${n}::uuid IS NULL AND UPPER({state_col}) = UPPER(${n + 1})))")


def _scope_employee(n: int) -> str:
    """Matter-scope predicate for tables reached via ``employees e``.
    Exact work_location_id match preferred; work_state fallback when that FK
    is NULL (nullable, never backfilled) — same convention as
    compliance_service.get_locations."""
    return (f" AND ((${n}::uuid IS NULL AND ${n + 1}::varchar IS NULL)"
            f" OR (${n}::uuid IS NOT NULL AND (e.work_location_id = ${n}"
            f" OR (e.work_location_id IS NULL AND UPPER(e.work_state) = UPPER(${n + 1}))))"
            f" OR (${n}::uuid IS NULL AND UPPER(e.work_state) = UPPER(${n + 1})))")


_UUID_RE_SQL = "'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'"


def _scope_er_involved(n: int) -> str:
    """Matter-scope predicate for er_cases (alias ``ec``), whose only employee
    link is the JSONB ``involved_employees`` array (elements carry an
    ``employee_id`` key — see er_copilot._resolve_involved_parties).

    A case naming NO employees stays IN scope — opposite default from the
    employee-linked tables (where every row names an employee): an
    unattributable ER case silently dropped from a legal corpus is worse than
    over-inclusion. The regex guard keeps a malformed employee_id string from
    crashing the uuid cast."""
    return (
        f" AND ((${n}::uuid IS NULL AND ${n + 1}::varchar IS NULL)"
        f" OR jsonb_array_length(COALESCE(ec.involved_employees, '[]'::jsonb)) = 0"
        f" OR EXISTS ("
        f"   SELECT 1 FROM jsonb_array_elements(COALESCE(ec.involved_employees, '[]'::jsonb)) ie"
        f"   JOIN employees e ON (ie->>'employee_id') ~ {_UUID_RE_SQL}"
        f"                   AND e.id = (ie->>'employee_id')::uuid"
        f"   WHERE (${n}::uuid IS NOT NULL AND (e.work_location_id = ${n}"
        f"          OR (e.work_location_id IS NULL AND UPPER(e.work_state) = UPPER(${n + 1}))))"
        f"      OR (${n}::uuid IS NULL AND UPPER(e.work_state) = UPPER(${n + 1}))))")


async def _src_incidents(conn, company_id, start, end, loc_id, state, topic=_BROAD) -> list[dict]:
    rows = await conn.fetch(
        f"""
        SELECT i.id, i.incident_number, i.title, i.incident_type, i.severity, i.status, i.occurred_at
        FROM ir_incidents i
        LEFT JOIN business_locations bl ON bl.id = i.location_id
        WHERE i.company_id = $1
          AND ($2::date IS NULL OR i.occurred_at >= $2)
          AND ($3::date IS NULL OR i.occurred_at < ($3::date + 1))
          {_scope_direct("i.location_id", "bl.state", 4)}
          {_topic_filter("i.incident_type", 6)}
        ORDER BY i.occurred_at DESC NULLS LAST
        """,
        company_id, start, end, loc_id, state, topic.incidents, _INCIDENT_TYPES,
    )
    return [{
        "cid": f"incident:{r['id']}",
        "ref": r["incident_number"],
        "summary": f"{r['title']} — type {_hum(r['incident_type'])}, severity {_hum(r['severity'])}, status {_hum(r['status'])}",
        "when": _dt(r["occurred_at"]),
        "when_iso": _iso(r["occurred_at"]),
    } for r in rows]


async def _src_er_cases(conn, company_id, start, end, loc_id, state, topic=_BROAD) -> list[dict]:
    # The SQL allowlist can only see the category, and for ER that is frequently
    # a bucket rather than a subject: "other" and "policy_violation" are in every
    # theory's allowlist precisely because they might be about anything. A HIPAA
    # or FMLA-interference case filed under either one passed the filter legally
    # and landed in a wage-and-hour corpus. Where the category doesn't speak, the
    # case text does — demote only on a clear other-subject read.
    rows = await conn.fetch(
        f"""
        SELECT ec.id, ec.case_number, ec.title, ec.description, ec.category,
               ec.status, ec.outcome, ec.created_at
        FROM er_cases ec
        WHERE ec.company_id = $1
          AND ($2::date IS NULL OR ec.created_at >= $2)
          AND ($3::date IS NULL OR ec.created_at < ($3::date + 1))
          {_scope_er_involved(4)}
          {_topic_filter("ec.category", 6)}
        ORDER BY ec.created_at DESC NULLS LAST
        """,
        company_id, start, end, loc_id, state, topic.er, _ER_CATEGORIES,
    )
    rows = _demote_off_subject(rows, topic.slug, topic.er, _ER_CATEGORIES, "category",
                               "title", "description", generic=_GENERIC_ER_CATEGORIES)
    return [{
        "cid": f"er_case:{r['id']}",
        "ref": r["case_number"],
        "summary": f"{r['title']} — {_hum(r['category'])}, status {_hum(r['status'])}"
                   + (f", outcome {_hum(r['outcome'])}" if r["outcome"] else ""),
        "when": _dt(r["created_at"]),
        "when_iso": _iso(r["created_at"]),
    } for r in rows]


async def _src_compliance(conn, company_id, start, end, loc_id, state, topic=_BROAD) -> list[dict]:
    # Current requirement state per location = proof of what the company tracks /
    # the protocol it follows. Joined via business_locations (requirements carry
    # location_id, not company_id). Not date-filtered — it's current posture —
    # so the scope params bind $2/$3 here, not $4/$5.
    # The category vocabulary is NOT closed: compliance_service's Specialization
    # Research Wizard has Gemini mint snake_case keys outside CATEGORY_KEYS and
    # writes them onto requirements. Those survive _topic_filter's passthrough
    # arm — a hospital's `cardiac_catheterization_safety` requirement belongs in a
    # safety matter's corpus — but they are then read as text: the same minted key
    # naming a plainly different subject (`hipaa_privacy_notices` in a wage matter)
    # is demoted. Unclassifiable keys still pass, as before.
    #
    # Deliberately NOT codified-gated (platform_settings.tenant_codified_only),
    # unlike every tenant-facing compliance read. The claim is different: the tab
    # tells a business "this is the law you must follow", which an uncited row
    # cannot support; this tells counsel "here is what the company was tracking
    # on that date", and an uncited row is still true evidence of that. Gating
    # here would quietly shrink an attorney's evidence packet — the failure mode
    # runs the opposite direction, so it stays open.
    rows = await conn.fetch(
        f"""
        SELECT cr.id, cr.title, cr.category, cr.current_value, cr.jurisdiction_name,
               cr.last_changed_at, bl.name AS location_name, jr.statute_citation
        FROM compliance_requirements cr
        JOIN business_locations bl ON bl.id = cr.location_id
        LEFT JOIN jurisdiction_requirements jr
            ON jr.id = cr.jurisdiction_requirement_id AND jr.status = 'active'
        WHERE bl.company_id = $1
          {_scope_direct("cr.location_id", "bl.state", 2)}
          {_topic_filter("cr.category", 4)}
        ORDER BY cr.last_changed_at DESC NULLS LAST
        """,
        company_id, loc_id, state, topic.compliance, _COMPLIANCE_CATEGORIES,
    )
    rows = _demote_off_subject(rows, topic.slug, topic.compliance, _COMPLIANCE_CATEGORIES,
                              "category", "title")
    return [{
        "cid": f"compliance_req:{r['id']}",
        "ref": _hum(r["category"]),
        "summary": f"{r['title']}"
                   + (f" = {r['current_value']}" if r["current_value"] else "")
                   + (f" ({r['jurisdiction_name']})" if r["jurisdiction_name"] else "")
                   + (f" @ {r['location_name']}" if r["location_name"] else "")
                   + (f" [{r['statute_citation']}]" if r["statute_citation"] else ""),
        "when": _dt(r["last_changed_at"]),
        "when_iso": _iso(r["last_changed_at"]),
    } for r in rows]


async def _src_discipline(conn, company_id, start, end, loc_id, state, topic=_BROAD) -> list[dict]:
    # Infraction types are per-company configurable (discipline_policy_mapping),
    # so _INFRACTIONS — the DEFAULTS — is a floor, not the vocabulary. A
    # behavioral-health tenant's `hipaa` / `patient_safety` infractions are
    # unknown here, passed the SQL filter as "company-defined", and filled a
    # wage-and-hour corpus. The slug names its own subject; read it.
    rows = await conn.fetch(
        f"""
        SELECT pd.id, pd.discipline_type, pd.infraction_type, pd.description,
               pd.severity, pd.status, pd.issued_date
        FROM progressive_discipline pd
        JOIN employees e ON e.id = pd.employee_id
        WHERE pd.company_id = $1
          AND ($2::date IS NULL OR pd.issued_date >= $2)
          AND ($3::date IS NULL OR pd.issued_date < ($3::date + 1))
          {_scope_employee(4)}
          {_topic_filter("pd.infraction_type", 6)}
        ORDER BY pd.issued_date DESC NULLS LAST
        """,
        company_id, start, end, loc_id, state, topic.discipline, _INFRACTIONS,
    )
    rows = _demote_off_subject(rows, topic.slug, topic.discipline, _INFRACTIONS,
                               "infraction_type", "description",
                               generic=_GENERIC_INFRACTIONS)
    return [{
        "cid": f"discipline:{r['id']}",
        "ref": _hum(r["discipline_type"]),
        "summary": f"{_hum(r['discipline_type'])}"
                   + (f" for {_hum(r['infraction_type'])}" if r["infraction_type"] else "")
                   + (f", severity {_hum(r['severity'])}" if r["severity"] else "")
                   + f", status {_hum(r['status'])}",
        "when": _dt(r["issued_date"]),
        "when_iso": _iso(r["issued_date"]),
    } for r in rows]


async def _src_training(conn, company_id, start, end, loc_id, state, topic=_BROAD) -> list[dict]:
    # Deliberately NOT topic-filtered. Training / policy acknowledgments /
    # accommodations are the exculpatory half of the record — "we trained on
    # this, they signed for it" — and counsel wants the full set regardless of
    # theory. They are also small; noise isn't the failure mode here.
    rows = await conn.fetch(
        f"""
        SELECT tr.id, tr.title, tr.training_type, tr.status, tr.completed_date,
               tr.expiration_date, tr.source_type, tr.source_ref
        FROM training_records tr
        JOIN employees e ON e.id = tr.employee_id
        WHERE tr.company_id = $1
          AND ($2::date IS NULL OR COALESCE(tr.completed_date, tr.created_at) >= $2)
          AND ($3::date IS NULL OR COALESCE(tr.completed_date, tr.created_at) < ($3::date + 1))
          {_scope_employee(4)}
        ORDER BY tr.completed_date DESC NULLS LAST
        """,
        company_id, start, end, loc_id, state,
    )
    return [{
        "cid": f"training:{r['id']}",
        "ref": _hum(r["training_type"]) or "Training",
        "summary": f"{r['title']} — status {_hum(r['status'])}"
                   + (f", expires {_dt(r['expiration_date'])}" if r["expiration_date"] else "")
                   # Remedial provenance is exactly the "we responded" fact a
                   # defense memo wants to cite — surface it in the summary
                   # line rather than only on the detail fetch.
                   + (f" — assigned after {r['source_type']} "
                      f"{r['source_ref']}" if r["source_type"] in ("incident", "discipline") and r["source_ref"] else ""),
        "when": _dt(r["completed_date"]),
        "when_iso": _iso(r["completed_date"]),
    } for r in rows]


async def _src_policy_ack(conn, company_id, start, end, loc_id, state, topic=_BROAD) -> list[dict]:
    # loc_id/state/topic unused: policies are company-wide — no location concept
    # exists anywhere in the policies schema. Stays unscoped by design.
    rows = await conn.fetch(
        """
        SELECT ps.id, ps.signer_name, ps.signed_at, p.title AS policy_title
        FROM policy_signatures ps
        JOIN policies p ON p.id = ps.policy_id
        WHERE p.company_id = $1 AND ps.status = 'signed'
          AND ($2::date IS NULL OR ps.signed_at >= $2)
          AND ($3::date IS NULL OR ps.signed_at < ($3::date + 1))
        ORDER BY ps.signed_at DESC NULLS LAST
        """,
        company_id, start, end,
    )
    return [{
        "cid": f"policy_ack:{r['id']}",
        "ref": "policy acknowledgment",
        "summary": f"{r['policy_title'] or 'Policy'} acknowledged by {r['signer_name'] or 'employee'}",
        "when": _dt(r["signed_at"]),
        "when_iso": _iso(r["signed_at"]),
    } for r in rows]


async def _src_accommodations(conn, company_id, start, end, loc_id, state, topic=_BROAD) -> list[dict]:
    rows = await conn.fetch(
        f"""
        SELECT ac.id, ac.case_number, ac.title, ac.status, ac.disability_category, ac.created_at
        FROM accommodation_cases ac
        JOIN employees e ON e.id = ac.employee_id
        WHERE ac.org_id = $1
          AND ($2::date IS NULL OR ac.created_at >= $2)
          AND ($3::date IS NULL OR ac.created_at < ($3::date + 1))
          {_scope_employee(4)}
        ORDER BY ac.created_at DESC NULLS LAST
        """,
        company_id, start, end, loc_id, state,
    )
    return [{
        "cid": f"accommodation:{r['id']}",
        "ref": r["case_number"],
        "summary": f"{r['title']} — {_hum(r['disability_category'])}, status {_hum(r['status'])}",
        "when": _dt(r["created_at"]),
        "when_iso": _iso(r["created_at"]),
    } for r in rows]
async def _src_leave(conn, company_id, start, end, loc_id, state, topic=_BROAD) -> list[dict]:
    # Leave is the companion evidence for FMLA-interference and retaliation
    # theories: what leave was taken, when, and how it was dispositioned is
    # exactly what the timeline turns on.
    #
    # `reason`, `denial_reason` and `notes` are deliberately NOT selected —
    # free-text medical detail has no business in an AI corpus, and the dates
    # carry the evidentiary weight without it. The packet's appendix could
    # surface more (attorney-facing); the model never sees it.
    #
    # NOTE: leave_requests keys on `org_id`, not `company_id` (d0a8f93f3fd0).
    # Window on the leave's span, not its creation: a leave that started before
    # the window but ran into it is in scope. `end_date` is NULL for an
    # open-ended leave, so it falls back to the return date and then to today —
    # collapsing to `start_date` would drop the still-running leave that began
    # before the window, which on an interference matter is the whole subject.
    # Over-inclusive for a denied/cancelled request with no end date; that is the
    # module's standing trade (a record wrongly absent from a legal corpus is
    # worse than one wrongly present).
    rows = await conn.fetch(
        f"""
        SELECT lr.id, lr.leave_type, lr.status, lr.start_date, lr.end_date,
               lr.expected_return_date, lr.actual_return_date, lr.intermittent,
               e.first_name, e.last_name
        FROM leave_requests lr
        JOIN employees e ON e.id = lr.employee_id
        WHERE lr.org_id = $1
          AND ($2::date IS NULL OR COALESCE(lr.end_date, lr.actual_return_date, CURRENT_DATE) >= $2)
          AND ($3::date IS NULL OR lr.start_date < ($3::date + 1))
          {_scope_employee(4)}
        ORDER BY lr.start_date DESC NULLS LAST
        """,
        company_id, start, end, loc_id, state,
    )
    return [{
        "cid": f"leave:{r['id']}",
        "ref": f"{_hum_acronym(r['leave_type'])} leave",
        "summary": f"{_hum_acronym(r['leave_type'])} leave for {_emp_name(r, 'an employee')} — status {_hum(r['status'])}"
                   + f", {_dt(r['start_date'])} to "
                   + (_dt(r["end_date"]) if r["end_date"] else "open-ended")
                   + (", intermittent" if r["intermittent"] else "")
                   + (f", returned {_dt(r['actual_return_date'])}" if r["actual_return_date"]
                      else (f", expected return {_dt(r['expected_return_date'])}"
                            if r["expected_return_date"] else "")),
        "when": _dt(r["start_date"]),
        "when_iso": _iso(r["start_date"]),
    } for r in rows]


async def _src_agency_charges(conn, company_id, start, end, loc_id, state, topic=_BROAD) -> list[dict]:
    # The most on-topic table the pilot has for its own declared matter types
    # (eeoc_charge, single_plaintiff, class_action) — prior charge history and
    # how each resolved. Resolution amounts are included: settlement history is
    # legitimate defense context, not a secret from counsel.
    rows = await conn.fetch(
        f"""
        SELECT agc.id, agc.charge_type, agc.charge_number, agc.agency_name, agc.status,
               agc.filing_date, agc.resolution_amount, agc.resolution_date,
               e.first_name, e.last_name
        FROM agency_charges agc
        JOIN employees e ON e.id = agc.employee_id
        WHERE agc.company_id = $1
          AND ($2::date IS NULL OR agc.filing_date >= $2)
          AND ($3::date IS NULL OR agc.filing_date < ($3::date + 1))
          {_scope_employee(4)}
        ORDER BY agc.filing_date DESC NULLS LAST
        """,
        company_id, start, end, loc_id, state,
    )
    return [{
        "cid": f"charge:{r['id']}",
        "ref": r["charge_number"] or r["agency_name"] or f"{_hum_acronym(r['charge_type'])} charge",
        "summary": f"{_hum_acronym(r['charge_type'])} charge"
                   + (f" filed with {r['agency_name']}" if r["agency_name"] else "")
                   + f" naming {_emp_name(r, 'an employee')} — status {_hum(r['status'])}"
                   + (f", resolved {_dt(r['resolution_date'])}" if r["resolution_date"] else "")
                   + (f" for {_money(r['resolution_amount'])}"
                      if r["resolution_amount"] is not None else ""),
        "when": _dt(r["filing_date"]),
        "when_iso": _iso(r["filing_date"]),
    } for r in rows]


async def _src_pre_termination(conn, company_id, start, end, loc_id, state, topic=_BROAD) -> list[dict]:
    # Direct evidence that diligence ran BEFORE the separation — the point of the
    # record. The AI narrative and dimension detail stay out of the corpus; band,
    # score and outcome say what happened.
    rows = await conn.fetch(
        f"""
        SELECT pt.id, pt.overall_score, pt.overall_band, pt.outcome, pt.is_voluntary,
               pt.acknowledged, pt.computed_at, e.first_name, e.last_name
        FROM pre_termination_checks pt
        JOIN employees e ON e.id = pt.employee_id
        WHERE pt.company_id = $1
          AND ($2::date IS NULL OR pt.computed_at >= $2)
          AND ($3::date IS NULL OR pt.computed_at < ($3::date + 1))
          {_scope_employee(4)}
        ORDER BY pt.computed_at DESC NULLS LAST
        """,
        company_id, start, end, loc_id, state,
    )
    return [{
        "cid": f"preterm:{r['id']}",
        "ref": "Pre-termination review",
        "summary": f"Pre-termination risk review for {_emp_name(r, 'an employee')} — risk band "
                   f"{_hum(r['overall_band'])} (score {r['overall_score']})"
                   + (f", outcome {_hum(r['outcome'])}" if r["outcome"] else "")
                   + (", recorded as a voluntary separation" if r["is_voluntary"]
                      else ", recorded as an involuntary separation"),
        "when": _dt(r["computed_at"]),
        "when_iso": _iso(r["computed_at"]),
    } for r in rows]


async def _src_separations(conn, company_id, start, end, loc_id, state, topic=_BROAD) -> list[dict]:
    # OWBPA/ADEA compliance lives in these columns — consideration and revocation
    # windows are the release's validity, so they belong in the summary, not just
    # the appendix. Window on when the agreement was presented (falling back to
    # when it was created), which is the act with legal significance.
    rows = await conn.fetch(
        f"""
        SELECT sa.id, sa.status, sa.severance_weeks, sa.severance_amount,
               sa.is_adea_applicable, sa.is_group_layoff, sa.consideration_period_days,
               sa.revocation_period_days, sa.presented_date, sa.signed_date,
               sa.effective_date, sa.revoked_date, sa.created_at,
               e.first_name, e.last_name
        FROM separation_agreements sa
        JOIN employees e ON e.id = sa.employee_id
        WHERE sa.company_id = $1
          AND ($2::date IS NULL OR COALESCE(sa.presented_date, sa.created_at::date) >= $2)
          AND ($3::date IS NULL OR COALESCE(sa.presented_date, sa.created_at::date) < ($3::date + 1))
          {_scope_employee(4)}
        ORDER BY COALESCE(sa.presented_date, sa.created_at::date) DESC NULLS LAST
        """,
        company_id, start, end, loc_id, state,
    )
    out = []
    for r in rows:
        bits = [f"status {_hum(r['status'])}"]
        if r["severance_weeks"] is not None:
            bits.append(f"{r['severance_weeks']} week(s) severance")
        if r["severance_amount"] is not None:
            bits.append(_money(r["severance_amount"]))
        if r["is_adea_applicable"]:
            bits.append(f"ADEA/OWBPA release ({r['consideration_period_days'] or '—'}-day "
                        f"consideration, {r['revocation_period_days'] or '—'}-day revocation)")
        if r["is_group_layoff"]:
            bits.append("group layoff")
        if r["presented_date"]:
            bits.append(f"presented {_dt(r['presented_date'])}")
        if r["signed_date"]:
            bits.append(f"signed {_dt(r['signed_date'])}")
        if r["revoked_date"]:
            bits.append(f"revoked {_dt(r['revoked_date'])}")
        # Date the record the same way the query windows and orders it. Keying
        # `when` on presented_date alone left a drafted-but-never-presented
        # agreement dateless — dropped from the chronology, "—" in the evidence
        # index — even though it was selected on its created_at.
        dated = r["presented_date"] or r["created_at"]
        if not r["presented_date"]:
            bits.append("not presented; drafted " + _dt(r["created_at"]))
        out.append({
            "cid": f"separation:{r['id']}",
            "ref": "Separation agreement",
            "summary": f"Separation agreement with {_emp_name(r, 'an employee')} — " + ", ".join(bits),
            "when": _dt(dated),
            "when_iso": _iso(dated),
        })
    return out


async def _src_post_term_claims(conn, company_id, start, end, loc_id, state, topic=_BROAD) -> list[dict]:
    rows = await conn.fetch(
        f"""
        SELECT ptc.id, ptc.claim_type, ptc.status, ptc.filed_date,
               ptc.resolution_amount, ptc.resolution_date, e.first_name, e.last_name
        FROM post_termination_claims ptc
        JOIN employees e ON e.id = ptc.employee_id
        WHERE ptc.company_id = $1
          AND ($2::date IS NULL OR ptc.filed_date >= $2)
          AND ($3::date IS NULL OR ptc.filed_date < ($3::date + 1))
          {_scope_employee(4)}
        ORDER BY ptc.filed_date DESC NULLS LAST
        """,
        company_id, start, end, loc_id, state,
    )
    return [{
        "cid": f"ptclaim:{r['id']}",
        "ref": _hum(r["claim_type"]) or "Post-termination claim",
        "summary": f"{_hum(r['claim_type'])} claim by {_emp_name(r, 'an employee')} after separation — "
                   f"status {_hum(r['status'])}"
                   + (f", resolved {_dt(r['resolution_date'])}" if r["resolution_date"] else "")
                   + (f" for {_money(r['resolution_amount'])}"
                      if r["resolution_amount"] is not None else ""),
        "when": _dt(r["filed_date"]),
        "when_iso": _iso(r["filed_date"]),
    } for r in rows]


# --------------------------------------------------------------------------- #
# Employment-practices registers (`workforce_compliance`).
#
# Four small registers the tenant keeps about ITSELF — a pay-equity study log, an
# AI hiring-tool bias-audit register, per-state pay-transparency posting posture,
# and a biometric/BIPA consent inventory. Each is the documentary answer to a
# claim type this pilot already models: an equal-pay class action asks whether the
# employer ever studied its own pay, a disparate-impact hiring charge asks whether
# the screening tool was audited, and BIPA suits turn entirely on whether written
# consent was obtained before collection.
#
# They are CURRENT POSTURE, not events, so — like `_src_compliance` — none of them
# is date-filtered: the study that predates the evidence window is still the study
# the company was operating under during it, and windowing it out would answer
# "did you ever look at this?" with a false no. Scope params therefore bind at
# $2/$3, not $4/$5.
#
# None is topic-filtered either, for the reason `_src_training` gives: these are
# the exculpatory half of the record ("we audited, we studied, we obtained
# consent"), counsel wants the full set whatever the theory, and the registers are
# small enough that noise is not the failure mode.
#
# `is_overdue` / cadence flags are recomputed here from the due date rather than
# read from their stored columns: those are stamped at write time by
# `workforce_compliance.audit_dates` and go stale as the calendar moves, and a
# legal exhibit must not report "current" from a value that was true last year.
# --------------------------------------------------------------------------- #

def _overdue_sql(col: str) -> str:
    return f"({col} IS NOT NULL AND {col} < CURRENT_DATE)"


async def _src_pay_equity(conn, company_id, start, end, loc_id, state, topic=_BROAD) -> list[dict]:
    # Company-wide (no location column). `gap_pct` and `dispersion_pct` are
    # deliberately rendered as different sentences and never merged: the first is
    # a measured protected-class gap, the second only the share of roles whose pay
    # spread exceeds a threshold. Migration payequity02 exists because conflating
    # them reported a "40% gap" to underwriters; doing it in an attorney-facing
    # exhibit would be materially worse.
    rows = await conn.fetch(
        f"""
        SELECT pe.id, pe.review_date, pe.scope, pe.methodology, pe.gap_pct,
               pe.dispersion_pct, pe.remediation, pe.next_due_date,
               {_overdue_sql("pe.next_due_date")} AS overdue
        FROM pay_equity_reviews pe
        WHERE pe.company_id = $1
        ORDER BY pe.review_date DESC NULLS LAST
        """,
        company_id,
    )
    out = []
    for r in rows:
        bits = []
        if r["scope"]:
            bits.append(f"scope {r['scope']}")
        if r["methodology"]:
            bits.append(f"methodology {r['methodology']}")
        if r["gap_pct"] is not None:
            bits.append(f"measured adjusted pay gap {r['gap_pct']}%")
        if r["dispersion_pct"] is not None:
            bits.append(f"{r['dispersion_pct']}% of roles flagged by the pay-dispersion "
                        f"screen (a screen, not a measured protected-class gap)")
        if r["remediation"]:
            bits.append(f"remediation: {r['remediation']}")
        if r["next_due_date"]:
            bits.append(f"next study due {_dt(r['next_due_date'])}"
                        + (" — overdue" if r["overdue"] else ""))
        out.append({
            "cid": f"payequity:{r['id']}",
            "ref": "Pay-equity study",
            "summary": "Pay-equity study"
                       + (f" dated {_dt(r['review_date'])}" if r["review_date"] else " (undated)")
                       + (" — " + ", ".join(bits) if bits else ""),
            "when": _dt(r["review_date"]),
            "when_iso": _iso(r["review_date"]),
        })
    return out


async def _src_hiring_ai_audits(conn, company_id, start, end, loc_id, state, topic=_BROAD) -> list[dict]:
    # Company-wide. A tool that has NEVER been audited (last_audit_date NULL) is
    # the most probative row in this register for a disparate-impact charge, so it
    # is surfaced explicitly rather than dropped for having no date.
    rows = await conn.fetch(
        f"""
        SELECT ha.id, ha.tool_name, ha.vendor, ha.purpose, ha.last_audit_date,
               ha.next_due_date, {_overdue_sql("ha.next_due_date")} AS overdue
        FROM hiring_ai_audits ha
        WHERE ha.company_id = $1
        ORDER BY ha.last_audit_date DESC NULLS LAST
        """,
        company_id,
    )
    out = []
    for r in rows:
        bits = []
        if r["vendor"]:
            bits.append(f"vendor {r['vendor']}")
        if r["purpose"]:
            bits.append(f"used for {r['purpose']}")
        if r["last_audit_date"]:
            bits.append(f"last bias audit {_dt(r['last_audit_date'])}")
        else:
            bits.append("no bias audit recorded")
        if r["next_due_date"]:
            bits.append(f"next due {_dt(r['next_due_date'])}"
                        + (" — overdue" if r["overdue"] else ""))
        out.append({
            "cid": f"aiaudit:{r['id']}",
            "ref": "AI hiring-tool audit",
            "summary": f"AI hiring tool {r['tool_name']} — " + ", ".join(bits),
            "when": _dt(r["last_audit_date"]),
            "when_iso": _iso(r["last_audit_date"]),
        })
    return out


async def _src_pay_transparency(conn, company_id, start, end, loc_id, state, topic=_BROAD) -> list[dict]:
    # Rows ARE per-state, so the matter's state scope applies directly — no
    # location join needed. `state` is populated from the matter's location when
    # one is set (gather_evidence resolves location→state first), so this scopes
    # correctly under either axis, and falls open when neither resolves a state.
    rows = await conn.fetch(
        """
        SELECT pt.id, pt.state, pt.status, pt.postings_include_ranges, pt.note, pt.updated_at
        FROM pay_transparency_status pt
        WHERE pt.company_id = $1
          AND ($2::varchar IS NULL OR UPPER(pt.state) = UPPER($2))
        ORDER BY pt.state
        """,
        company_id, state,
    )
    out = []
    for r in rows:
        # 'na' means the state has no posting law to be compliant WITH, so it
        # gets its own phrase: `_hum` renders it "Na", and the ranges clause
        # below would otherwise report a posting failure against a rule that
        # does not apply.
        na = (r["status"] or "").lower() == "na"
        if na:
            status = "not applicable in this state"
        else:
            status = _hum(r["status"]) + (
                ", job postings include pay ranges" if r["postings_include_ranges"]
                else ", job postings do not include pay ranges")
        out.append({
            "cid": f"paytransp:{r['id']}",
            "ref": f"{r['state']} pay transparency",
            "summary": f"{r['state']} pay-transparency posting status: {status}"
                       + (f" — {r['note']}" if r["note"] else ""),
            "when": _dt(r["updated_at"]),
            "when_iso": _iso(r["updated_at"]),
        })
    return out


async def _src_biometric_consent(conn, company_id, start, end, loc_id, state, topic=_BROAD) -> list[dict]:
    # `location_id` is nullable metadata here, not the row's identity, so the
    # standard `_scope_direct` predicate is wrong: its "no attributable location
    # is excluded while a scope is active" arm would drop a company-wide
    # fingerprint-clock inventory row from a location-scoped BIPA corpus. The
    # NULL arm below keeps it, matching `_scope_er_involved`'s reasoning.
    rows = await conn.fetch(
        """
        SELECT bc.id, bc.collection_type, bc.purpose, bc.consent_obtained,
               bc.consent_obtained_date, bc.consent_method, bc.retention_policy,
               bc.is_active, bl.name AS location_name
        FROM biometric_consent_points bc
        LEFT JOIN business_locations bl ON bl.id = bc.location_id
        WHERE bc.company_id = $1
          AND (($2::uuid IS NULL AND $3::varchar IS NULL)
               OR bc.location_id IS NULL
               OR ($2::uuid IS NOT NULL AND bc.location_id = $2)
               OR ($2::uuid IS NULL AND UPPER(bl.state) = UPPER($3)))
        ORDER BY bc.consent_obtained_date DESC NULLS LAST
        """,
        company_id, loc_id, state,
    )
    out = []
    for r in rows:
        bits = [f"collection {_hum(r['collection_type'])}"]
        if r["purpose"]:
            bits.append(f"purpose {r['purpose']}")
        # Consent obtained / not obtained is the whole claim under BIPA — state it
        # flatly in both directions rather than only on the affirmative.
        if r["consent_obtained"]:
            bits.append("consent obtained"
                        + (f" {_dt(r['consent_obtained_date'])}" if r["consent_obtained_date"] else "")
                        + (f" ({_hum(r['consent_method'])})" if r["consent_method"] else ""))
        else:
            bits.append("no consent recorded")
        if r["retention_policy"]:
            bits.append(f"retention: {r['retention_policy']}")
        bits.append("active" if r["is_active"] else "discontinued")
        out.append({
            "cid": f"biometric:{r['id']}",
            "ref": f"{_hum(r['collection_type'])} collection",
            "summary": "Biometric collection point"
                       + (f" @ {r['location_name']}" if r["location_name"] else " (company-wide)")
                       + " — " + ", ".join(bits),
            "when": _dt(r["consent_obtained_date"]),
            "when_iso": _iso(r["consent_obtained_date"]),
        })
    return out


async def _src_compliance_alerts(conn, company_id, start, end, loc_id, state, topic=_BROAD) -> list[dict]:
    # Date-filtered (unlike _src_compliance's current-posture snapshot) — this
    # is deliberately a history: it shows the company was monitoring during
    # the matter window, not just what it tracks today.
    rows = await conn.fetch(
        f"""
        SELECT ca.id, ca.title, ca.severity, ca.status, ca.category, ca.deadline,
               ca.created_at, bl.name AS location_name
        FROM compliance_alerts ca
        JOIN business_locations bl ON bl.id = ca.location_id
        WHERE ca.company_id = $1
          AND ($2::date IS NULL OR ca.created_at >= $2)
          AND ($3::date IS NULL OR ca.created_at < ($3::date + 1))
          {_scope_direct("ca.location_id", "bl.state", 4)}
          {_topic_filter("ca.category", 6)}
        ORDER BY ca.created_at DESC
        LIMIT 100
        """,
        company_id, start, end, loc_id, state, topic.compliance, _COMPLIANCE_CATEGORIES,
    )
    rows = _demote_off_subject(rows, topic.slug, topic.compliance, _COMPLIANCE_CATEGORIES,
                               "category", "title")
    return [{
        "cid": f"compliance_alert:{r['id']}",
        "ref": _hum(r["category"]) or "Alert",
        "summary": f"{r['title']} — {_hum(r['severity'])}, {_hum(r['status'])}"
                   + (f", deadline {_dt(r['deadline'])}" if r["deadline"] else "")
                   + (f" @ {r['location_name']}" if r["location_name"] else ""),
        "when": _dt(r["created_at"]),
        "when_iso": _iso(r["created_at"]),
    } for r in rows]


async def _src_compliance_remediation(conn, company_id, start, end, loc_id, state, topic=_BROAD) -> list[dict]:
    # The remediation trail: issues the company detected AND resolved/dismissed
    # in-window. Strong defensive evidence — "we found the underpayment on 6/1
    # and corrected it by 6/14". Company-wide (no location link on the row).
    rows = await conn.fetch(
        """
        SELECT s.id, s.issue_key, s.source, s.severity, s.title, s.status,
               s.resolution_method, s.resolution_note, s.first_seen_at, s.resolved_at
        FROM compliance_issue_state s
        WHERE s.company_id = $1
          AND s.status IN ('resolved','dismissed')
          AND ($2::date IS NULL OR s.resolved_at >= $2)
          AND ($3::date IS NULL OR s.resolved_at < ($3::date + 1))
        ORDER BY s.resolved_at DESC
        LIMIT 100
        """,
        company_id, start, end,
    )
    return [{
        "cid": f"remediation:{r['id']}",
        "ref": _hum(r["source"]) or "Remediation",
        "summary": f"{r['title']} — {_hum(r['status'])} via {_hum(r['resolution_method']) or 'update'}"
                   + (f": {r['resolution_note']}" if r["resolution_note"] else "")
                   + (f" (flagged {_dt(r['first_seen_at'])})" if r["first_seen_at"] else ""),
        "when": _dt(r["resolved_at"]),
        "when_iso": _iso(r["resolved_at"]),
    } for r in rows]
